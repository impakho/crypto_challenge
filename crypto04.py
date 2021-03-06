#!/usr/bin/env python
from functools import partial
import itertools
import random
import struct
import sys
import urllib
import time

from Crypto.Cipher import AES

import md4
from md4 import int_array2str, U32

random.seed('matasano') #for reproducibility - will work with any seed


#http://docs.python.org/2/library/itertools.html#recipes
def grouper(n, iterable, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # grouper(3, 'ABCDEFG', 'x') --> ABC DEF Gxx
    args = [iter(iterable)] * n
    return itertools.izip_longest(fillvalue=fillvalue, *args)


def random_key(keylen):
    return ''.join(chr(random.randint(0,255)) for _ in xrange(keylen))


def xor_block(b1, b2):
    return ''.join(chr(ord(x) ^ ord(y)) for x,y in zip(b1, b2))


def xor_aes_ctr(key, nonce, data):
    def gen_keystream():
        aes = AES.new(key, mode=AES.MODE_ECB)
        for i in itertools.count():
            for c in aes.encrypt(struct.pack('<QQ', nonce, i)):
                yield c

    return ''.join(chr(ord(x) ^ ord(y)) for x,y in itertools.izip(data, gen_keystream()))


def pkcs7_pad(blocklen, data):
    padlen = blocklen - len(data) % blocklen
    return data + chr(padlen) * padlen


class PadException(Exception):
        pass

def pkcs7_strip(data):
    padchar = data[-1]
    padlen = ord(padchar)
    if padlen == 0 or not data.endswith(padchar * padlen):
        raise PadException
    return data[:-padlen]


def get_status(url):
    r = urllib.urlopen(url)
    status = r.getcode()
    r.read()
    r.close()
    return status


#https://github.com/ajalt/python-sha1
def sha1(message, h0=0x67452301, h1=0xEFCDAB89, h2=0x98BADCFE, h3=0x10325476, h4=0xC3D2E1F0, offset=0):
    """SHA-1 Hashing Function

    A custom SHA-1 hashing function implemented entirely in Python.

    Arguments:
        message: The input message string to hash.
        h0 ... h4: initial variables

    Returns:
        A hex SHA-1 digest of the input message.
    """

    def _left_rotate(n, b):
        return ((n << b) | (n >> (32 - b))) & 0xffffffff

    # Pre-processing:
    original_byte_len = len(message)
    original_bit_len = original_byte_len * 8
    # append the bit '1' to the message
    message += '\x80'

    # append 0 <= k < 512 bits '0', so that the resulting message length (in bits)
    #    is congruent to 448 (mod 512)
    message += '\x00' * ((56 - (original_byte_len + 1) % 64) % 64)

    # append length of message (before pre-processing), in bits, as 64-bit big-endian integer
    message += struct.pack('>Q', original_bit_len + (offset * 8))

    # Process the message in successive 512-bit chunks:
    # break message into 512-bit chunks
    for i in xrange(0, len(message), 64):
        w = [0] * 80
        # break chunk into sixteen 32-bit big-endian words w[i]
        for j in xrange(16):
            w[j] = struct.unpack('>I', message[i + j*4:i + j*4 + 4])[0]
        # Extend the sixteen 32-bit words into eighty 32-bit words:
        for j in xrange(16, 80):
            w[j] = _left_rotate(w[j-3] ^ w[j-8] ^ w[j-14] ^ w[j-16], 1)

        # Initialize hash value for this chunk:
        a = h0
        b = h1
        c = h2
        d = h3
        e = h4

        for i in xrange(80):
            if 0 <= i <= 19:
                # Use alternative 1 for f from FIPS PB 180-1 to avoid ~
                f = d ^ (b & (c ^ d))
                k = 0x5A827999
            elif 20 <= i <= 39:
                f = b ^ c ^ d
                k = 0x6ED9EBA1
            elif 40 <= i <= 59:
                f = (b & c) | (b & d) | (c & d)
                k = 0x8F1BBCDC
            elif 60 <= i <= 79:
                f = b ^ c ^ d
                k = 0xCA62C1D6

            a, b, c, d, e = ((_left_rotate(a, 5) + f + e + k + w[i]) & 0xffffffff,
                            a, _left_rotate(b, 30), c, d)

        # sAdd this chunk's hash to result so far:
        h0 = (h0 + a) & 0xffffffff
        h1 = (h1 + b) & 0xffffffff
        h2 = (h2 + c) & 0xffffffff
        h3 = (h3 + d) & 0xffffffff
        h4 = (h4 + e) & 0xffffffff

    # Produce the final hash value (big-endian):
    return '%08x%08x%08x%08x%08x' % (h0, h1, h2, h3, h4)


def authenticate(key, mac, message):
    return sha1(key + message) == mac


def cc25():
    """25. Break "random access read/write" AES CTR

Back to CTR. Encrypt the recovered plaintext from

    https://gist.github.com/3132853

(the ECB exercise) under CTR with a random key (for this exercise the
key should be unknown to you, but hold on to it).

Now, write the code that allows you to "seek" into the ciphertext,
decrypt, and re-encrypt with different plaintext. Expose this as a
function, like, "edit(ciphertext, key, offet, newtext)".

Imagine the "edit" function was exposed to attackers by means of an
API call that didn't reveal the key or the original plaintext; the
attacker has the ciphertext and controls the offset and "new text".

Recover the original plaintext.
"""
    #UNUSED: edit by decrypting first
    def edit_decrypt(key, nonce, ciphertext, offset, data):
        plain = xor_aes_ctr(key, nonce, ciphertext)
        data = ''.join((plain[:offset], data, plain[offset + len(data):]))
        return xor_aes_ctr(key, nonce, data)

    #don't really need to decrypt - just shift data, encrypt, and splice
    def edit(key, nonce, ciphertext, offset, data):
        edittext = xor_aes_ctr(key, nonce, '\x00' * offset + data)
        return ''.join((ciphertext[:offset], edittext[offset:], ciphertext[offset + len(data):]))

    #UNUSED: decrypt byte-by-byte (works, but slowly)
    def decrypt_bytes(ciphertext, fedit):
        output = ''
        chars = [chr(x) for x in xrange(256)]
        for i,x in enumerate(ciphertext):
            for c in chars:
                if fedit(ciphertext, i, c)[i] == x:
                    output += c
                    break
        return output

    #recover keystream by 'editing' with ciphertext worth of 0
    def decrypt(ciphertext, fedit):
        keystream = fedit(ciphertext, 0, '\x00' * len(ciphertext))
        return xor_block(keystream, ciphertext)

    with open('data/cc07.txt') as f:
        ciphertext = f.read().decode('base64')
    data = AES.new("YELLOW SUBMARINE", mode=AES.MODE_ECB).decrypt(ciphertext)

    key = random_key(16)
    nonce = random.randint(0, sys.maxint)
    ciphertext = xor_aes_ctr(key, nonce, data)
    fedit = partial(edit, key, nonce)
    print decrypt(ciphertext, fedit)


def cc26():
    """26. CTR bit flipping

There are people in the world that believe that CTR resists
bit flipping attacks of the kind to which CBC mode is susceptible.

Re-implement the CBC bitflipping exercise (16) from earlier to use CTR mode
instead of CBC mode. Inject an "admin=true" token.
"""
    def encrypt(key, nonce, data):
        prefix = "comment1=cooking%20MCs;userdata="
        suffix = ";comment2=%20like%20a%20pound%20of%20bacon"
        for c in ';=':
            data = data.replace(c, '%%%X' % ord(c))
        data = ''.join((prefix, data, suffix))
        return xor_aes_ctr(key, nonce, data)

    data = '?admin?true'
    print 'Input:', data

    key = random_key(16)
    nonce = random.randint(0, sys.maxint)
    ciphertext = encrypt(key, nonce, data)

    ciphertext = list(ciphertext)
    ciphertext[32] = chr(ord(ciphertext[32]) ^ (ord('?') ^ ord(';')))
    ciphertext[38] = chr(ord(ciphertext[38]) ^ (ord('?') ^ ord('=')))
    ciphertext = ''.join(ciphertext)

    plain = xor_aes_ctr(key, nonce, ciphertext)
    print 'Output:', plain
    print "Found ';admin=true;':", ';admin=true;' in plain


def cc27():
    """27. Recover the key from CBC with IV=Key

Take your code from the CBC exercise (16) and modify it so that it
repurposes the key for CBC encryption as the IV. Applications
sometimes use the key as an IV on the auspices that both the sender
and the receiver have to know the key already, and can save some space
by using it as both a key and an IV.

Using the key as an IV is insecure; an attacker that can modify
ciphertext in flight can get the receiver to decrypt a value that will
reveal the key.

The CBC code from exercise 16 encrypts a URL string. Verify each byte
of the plaintext for ASCII compliance (ie, look for high-ASCII
values). Noncompliant messages should raise an exception or return an
error that includes the decrypted plaintext (this happens all the time
in real systems, for what it's worth).

Use your code to encrypt a message that is at least 3 blocks long:

 AES-CBC(P_1, P_2, P_3) -> C_1, C_2, C_3

Modify the message (you are now the attacker):

 C_1, C_2, C_3 -> C_1, 0, C_1

Decrypt the message (you are now the receiver) and raise the
appropriate error if high-ASCII is found.

As the attacker, recovering the plaintext from the error, extract the
key:

 P'_1 XOR P'_3
"""
    def encrypt(key, iv, data):
        prefix = "comment1=cooking%20MCs;userdata="
        suffix = ";comment2=%20like%20a%20pound%20of%20bacon"
        for c in ';=':
            data = data.replace(c, '%%%X' % ord(c))
        data = pkcs7_pad(16, prefix + data + suffix)
        return AES.new(key, mode=AES.MODE_CBC, IV=iv).encrypt(data)

    def decrypt(key, iv, data):
        plain = pkcs7_strip(AES.new(key, mode=AES.MODE_CBC, IV=iv).decrypt(data))
        if all(ord(c) < 128 for c in plain):
            return True, plain
        return False, plain

    key = iv = random_key(16)
    print "Key %s == IV %s" % (key.encode('hex'), iv.encode('hex'))

    ciphertext = encrypt(key, iv, 'Ice')
    attacktext = ''.join((ciphertext[:16], '\x00' * 16, ciphertext[:16], ciphertext[48:]))
    ok, plain = decrypt(key, iv, attacktext)
    keyiv = xor_block(plain[:16], plain[32:48])
    print "Recovered Key/IV: %s" % keyiv.encode('hex')


def cc28():
    """28. Implement a SHA-1 keyed MAC

Find a SHA-1 implementation in the language you code in. Do not use
the SHA-1 implementation your language already provides (for instance,
don't use the "Digest" library in Ruby, or call OpenSSL; in Ruby,
you'd want a pure-Ruby SHA-1).

Write a function to authenticate a message under a secret key by using
a secret-prefix MAC, which is simply:

 SHA1(key || message)

Verify that you cannot tamper with the message without breaking the
MAC you've produced, and that you can't produce a new MAC without
knowing the secret key.
"""
    tests = [
        ('Original:', 'YELLOW SUBMARINE', "My posse's to the side yellin', Go Vanilla Go!"),
        ('Bad Key: ', 'ORANGE SUBMARINE', "My posse's to the side yellin', Go Vanilla Go!"),
        ('Bad Msg: ', 'YELLOW SUBMARINE', "My posse's to the side yellin', Stop Vanilla Stop!")]

    comment, key, msg = tests[0]
    mac = sha1(key + msg)
    for comment, key, msg in tests:
        print '%s %s %s\t%s' % (comment, key, msg, authenticate(key, mac, msg))


def cc29():
    """29. Break a SHA-1 keyed MAC using length extension

Secret-prefix SHA-1 MACs are trivially breakable.

The attack on secret-prefix SHA1 relies on the fact that you can take
the ouput of SHA-1 and use it as a new starting point for SHA-1, thus
taking an arbitrary SHA-1 hash and "feeding it more data".

Since the key precedes the data in secret-prefix, any additional data
you feed the SHA-1 hash in this fashion will appear to have been
hashed with the secret key.

To carry out the attack, you'll need to account for the fact that
SHA-1 is "padded" with the bit-length of the message; your forged
message will need to include that padding. We call this "glue
padding". The final message you actually forge will be:

         SHA1(key || original-message || glue-padding || new-message)

(where the final padding on the whole constructed message is implied)

Note that to generate the glue padding, you'll need to know the
original bit length of the message; the message itself is known to the
attacker, but the secret key isn't, so you'll need to guess at it.

This sounds more complicated than it is in practice.

To implement the attack, first write the function that computes the MD
padding of an arbitrary message and verify that you're generating the
same padding that your SHA-1 implementation is using. This should take
you 5-10 minutes.

Now, take the SHA-1 secret-prefix MAC of the message you want to forge
--- this is just a SHA-1 hash --- and break it into 32 bit SHA-1
registers (SHA-1 calls them "a", "b", "c", &c).

Modify your SHA-1 implementation so that callers can pass in new
values for "a", "b", "c" &c (they normally start at magic
numbers). With the registers "fixated", hash the additional data you
want to forge.

Using this attack, generate a secret-prefix MAC under a secret key
(choose a random word from /usr/share/dict/words or something) of the
string:

"comment1=cooking%20MCs;userdata=foo;comment2=%20like%20a%20pound%20of%20bacon"

Forge a variant of this message that ends with ";admin=true".
"""
    def sha1_pad(message):
        # Pre-processing:
        original_byte_len = len(message)
        original_bit_len = original_byte_len * 8
        # append the bit '1' to the message
        pad = '\x80'

        # append 0 <= k < 512 bits '0', so that the resulting message length (in bits)
        #    is congruent to 448 (mod 512)
        pad += '\x00' * ((56 - (original_byte_len + 1) % 64) % 64)

        # append length of message (before pre-processing), in bits, as 64-bit big-endian integer
        pad += struct.pack('>Q', original_bit_len)
        return pad

    key = random.choice(open('/usr/share/dict/words').readlines()).strip()
    message = "comment1=cooking%20MCs;userdata=foo;comment2=%20like%20a%20pound%20of%20bacon"
    mac = sha1(key + message)
    print 'Message:', message
    print 'MAC:', mac
    print 'Authenticated:', authenticate(key, mac, message)
    print

    registers = [int(''.join(h), 16) for h in grouper(8, mac)]
    suffix = ';admin=true'

    for keylen in xrange(0, 256):
        pad = sha1_pad(('A' * keylen) + message)
        offset = keylen + len(message + pad)
        attack_mac = sha1(suffix, *registers, offset=offset)
        attack_msg = message + pad + suffix
        if authenticate(key, attack_mac, attack_msg):
            print 'Message:', attack_msg
            print 'MAC:', attack_mac
            print 'Authenticated:', authenticate(key, attack_mac, attack_msg)
            break


def cc30():
    """30. Break an MD4 keyed MAC using length extension.

Second verse, same as the first, but use MD4 instead of SHA-1. Having
done this attack once against SHA-1, the MD4 variant should take much
less time; mostly just the time you'll spend Googling for an
implementation of MD4.
"""
    def md4_pad(message):
        s = [0x00] * 8
        padding = [0x00] * 64
        padding[0] = 0x80
        padlen, _, _ = U32(0), U32(0), U32(0)

        ilen = U32(len(message))
        len1 = ilen << 3
        len2 = ilen >> 29

        if (56 <= long(ilen)): padlen = U32(56 - long(ilen) + 64)
        else: padlen = U32(56 - long(ilen))

        pad = int_array2str(padding[:int(padlen)])

        s[0]= (len1)        & U32(0xFF)
        s[1]=((len1) >>  8) & U32(0xFF)
        s[2]=((len1) >> 16) & U32(0xFF)
        s[3]=((len1) >> 24) & U32(0xFF)
        s[4]= (len2)        & U32(0xFF)
        s[5]=((len2) >>  8) & U32(0xFF)
        s[6]=((len2) >> 16) & U32(0xFF)
        s[7]=((len2) >> 24) & U32(0xFF)
        pad += int_array2str(s)
        return pad

    def authenticate(key, mac, message):
        return md4.md4_hash(key + message) == mac

    key = random.choice(open('/usr/share/dict/words').readlines()).strip()
    message = "comment1=cooking%20MCs;userdata=foo;comment2=%20like%20a%20pound%20of%20bacon"
    mac = md4.md4_hash(key + message)
    print 'Message:', message
    print 'MAC:', md4.hexdigest(mac)
    print 'Authenticated:', authenticate(key, mac, message)
    print

    registers = struct.unpack('<LLLL', mac)
    suffix = ';admin=true'

    for keylen in xrange(0, 256):
        pad = md4_pad(('A' * keylen) + message)
        #print repr(pad)
        offset = keylen + len(message + pad)
        attack_mac = md4.md4_hash(suffix, *registers, offset=offset)
        attack_msg = message + pad + suffix
        if authenticate(key, attack_mac, attack_msg):
            print 'Message:', attack_msg
            print 'MAC:', md4.hexdigest(attack_mac)
            print 'Authenticated:', authenticate(key, attack_mac, attack_msg)
            break


def cc31():
    """31. Implement HMAC-SHA1 and break it with an artificial timing leak.

The psuedocode on Wikipedia should be enough. HMAC is very easy.

Using the web framework of your choosing (Sinatra, web.py, whatever),
write a tiny application that has a URL that takes a "file" argument
and a "signature" argument, like so:

http://localhost:9000/test?file=foo&signature=46b4ec586117154dacd49d664e5d63fdc88efb51

Have the server generate an HMAC key, and then verify that the
"signature" on incoming requests is valid for "file", using the "=="
operator to compare the valid MAC for a file with the "signature"
parameter (in other words, verify the HMAC the way any normal
programmer would verify it).

Write a function, call it "insecure_compare", that implements the ==
operation by doing byte-at-a-time comparisons with early exit (ie,
return false at the first non-matching byte).

In the loop for "insecure_compare", add a 50ms sleep (sleep 50ms after
each byte).

Use your "insecure_compare" function to verify the HMACs on incoming
requests, and test that the whole contraption works. Return a 500 if
the MAC is invalid, and a 200 if it's OK.

Using the timing leak in this application, write a program that
discovers the valid MAC for any file.
"""
    def recover_sig(url, fname):
        baseurl = url + '?file=%s&signature=%%s' % fname
        sig = ''
        while len(sig) < 40:
            c_time = {}
            for c in '0123456789abcdef':
                url = baseurl % sig + c
                tstart = time.time()
                get_status(url)
                tstop = time.time()
                c_time[c] = tstop - tstart
            t,c = max((t,c) for c,t in c_time.iteritems())
            sig += c
            print sig
        return sig


    url = 'http://localhost:9000/test31'
    fname = random.choice(open('/usr/share/dict/words').readlines()).strip()
    print 'Finding HMAC for:', fname
    sig = recover_sig(url, fname)
    url = url + '?file=%s&signature=%s' % (fname, sig)
    status = get_status(url)
    print status, fname, sig


def cc32():
    """32. Break HMAC-SHA1 with a slightly less artificial timing leak

Reduce the sleep in your "insecure_compare" until your previous
solution breaks. (Try 5ms to start.)

Now break it again.
"""
    print "5ms: do 5 rounds to increase delta between good and bad times"

    def recover_sig(url, fname):
        baseurl = url + '?file=%s&signature=%%s' % fname
        sig = ''
        while len(sig) < 40:
            c_time = {}
            for c in '0123456789abcdef':
                url = baseurl % sig + c
                tstart = time.time()
                for _ in xrange(5):
                    get_status(url)
                tstop = time.time()
                c_time[c] = tstop - tstart
            t,c = max((t,c) for c,t in c_time.iteritems())
            sig += c
            print sig
        return sig

    url = 'http://localhost:9000/test32'
    fname = random.choice(open('/usr/share/dict/words').readlines()).strip()
    print 'Finding HMAC for:', fname
    sig = recover_sig(url, fname)
    url = url + '?file=%s&signature=%s' % (fname, sig)
    status = get_status(url)
    print status, fname, sig


if __name__ == '__main__':
    for f in (cc25, cc26, cc27, cc28, cc29, cc30, cc31, cc32):
        print f.__doc__.split('\n')[0]
        f()
        print

