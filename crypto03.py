#!/usr/bin/env python
from collections import defaultdict
from functools import partial
import itertools
from operator import itemgetter
import random
import string
import struct
import time

from Crypto.Cipher import AES

random.seed('matasano') #for reproducibility - will work with any seed


#http://docs.python.org/2/library/itertools.html#recipes
def grouper(n, iterable, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # grouper(3, 'ABCDEFG', 'x') --> ABC DEF Gxx
    args = [iter(iterable)] * n
    return itertools.izip_longest(fillvalue=fillvalue, *args)


def pairwise(iterable):
    "s -> (s0,s1), (s1,s2), (s2, s3), ..."
    a, b = itertools.tee(iterable)
    next(b, None)
    return itertools.izip(a, b)


def window(seq, n=2):
    "Returns a sliding window (of width n) over data from the iterable"
    "   s -> (s0,s1,...s[n-1]), (s1,s2,...,sn), ...                   "
    it = iter(seq)
    result = tuple(itertools.islice(it, n))
    if len(result) == n:
        yield ''.join(result)
    for elem in it:
        result = result[1:] + (elem,)
        yield ''.join(result)


def random_key(keylen):
    return ''.join(chr(random.randint(0,255)) for _ in xrange(keylen))


def xor_block(b1, b2):
    return ''.join(chr(ord(x) ^ ord(y)) for x,y in zip(b1, b2))


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


def xor_aes_ctr(key, nonce, data):
    def gen_keystream():
        aes = AES.new(key, mode=AES.MODE_ECB)
        for i in itertools.count():
            for c in aes.encrypt(struct.pack('<QQ', nonce, i)):
                yield c

    return ''.join(chr(ord(x) ^ ord(y)) for x,y in itertools.izip(data, gen_keystream()))


def xor_data(key, data):
    "xor key with data, repeating key as necessary"
    if len(key) == 1:
        #shortcut
        key = ord(key)
        return ''.join(chr(ord(x) ^ key) for x in data)

    stream = itertools.cycle(key)
    return ''.join(chr(ord(x) ^ ord(y)) for x,y in itertools.izip(data, stream))


ok = set(string.letters + ' ')
def score_ratio(s):
    "ratio of letters+space to total length"
    count = sum(1 for x in s if x in ok)
    return count / float(len(s))


def score_decodings(keys, fscore, data):
    "return list of decodings, scored by fscore"
    scores = []
    for key in keys:
        plain = xor_data(key, data)
        score = fscore(plain)
        scores.append((score, key, plain))
    return sorted(scores, reverse=True)


class MersenneTwister(object):
    def __init__(self, seed):
        self.idx = 0
        self.MT = [seed]
        for i in xrange(1, 624):
            last = self.MT[i - 1]
            self.MT.append((0x6c078965 * (last ^ (last >> 30)) + i) & 0xFFFFFFFF)

    def generate(self):
        for i in xrange(624):
            y = (self.MT[i] & 0x80000000) + (self.MT[(i+1) % 624] & 0x7fffffff)
            self.MT[i] = self.MT[(i+397) % 624] ^ (y >> 1)
            if y % 2:
                self.MT[i] = self.MT[i] ^ 0x9908b0df

    def rand(self):
        if self.idx == 0:
            self.generate()

        y = self.MT[self.idx]
        y = y ^ (y >> 11)
        y = y ^ ((y << 7) & 0x9d2c5680)
        y = y ^ ((y << 15) & 0xefc60000)
        y = y ^ (y >> 18)

        self.idx = (self.idx + 1) % 624
        return y

    def snoop(self):
        print "MT[%s]: %s" % (self.idx, self.MT[self.idx])


def cc17():
    """17. The CBC padding oracle

Combine your padding code and your CBC code to write two functions.

The first function should select at random one of the following 10
strings:

MDAwMDAwTm93IHRoYXQgdGhlIHBhcnR5IGlzIGp1bXBpbmc=
MDAwMDAxV2l0aCB0aGUgYmFzcyBraWNrZWQgaW4gYW5kIHRoZSBWZWdhJ3MgYXJlIHB1bXBpbic=
MDAwMDAyUXVpY2sgdG8gdGhlIHBvaW50LCB0byB0aGUgcG9pbnQsIG5vIGZha2luZw==
MDAwMDAzQ29va2luZyBNQydzIGxpa2UgYSBwb3VuZCBvZiBiYWNvbg==
MDAwMDA0QnVybmluZyAnZW0sIGlmIHlvdSBhaW4ndCBxdWljayBhbmQgbmltYmxl
MDAwMDA1SSBnbyBjcmF6eSB3aGVuIEkgaGVhciBhIGN5bWJhbA==
MDAwMDA2QW5kIGEgaGlnaCBoYXQgd2l0aCBhIHNvdXBlZCB1cCB0ZW1wbw==
MDAwMDA3SSdtIG9uIGEgcm9sbCwgaXQncyB0aW1lIHRvIGdvIHNvbG8=
MDAwMDA4b2xsaW4nIGluIG15IGZpdmUgcG9pbnQgb2g=
MDAwMDA5aXRoIG15IHJhZy10b3AgZG93biBzbyBteSBoYWlyIGNhbiBibG93

generate a random AES key (which it should save for all future
encryptions), pad the string out to the 16-byte AES block size and
CBC-encrypt it under that key, providing the caller the ciphertext and
IV.

The second function should consume the ciphertext produced by the
first function, decrypt it, check its padding, and return true or
false depending on whether the padding is valid.

This pair of functions approximates AES-CBC encryption as its deployed
serverside in web applications; the second function models the
server's consumption of an encrypted session token, as if it was a
cookie.

It turns out that it's possible to decrypt the ciphertexts provided by
the first function.

The decryption here depends on a side-channel leak by the decryption
function.

The leak is the error message that the padding is valid or not.

You can find 100 web pages on how this attack works, so I won't
re-explain it. What I'll say is this:

The fundamental insight behind this attack is that the byte 01h is
valid padding, and occur in 1/256 trials of "randomized" plaintexts
produced by decrypting a tampered ciphertext.

02h in isolation is NOT valid padding.

02h 02h IS valid padding, but is much less likely to occur randomly
than 01h.

03h 03h 03h is even less likely.

So you can assume that if you corrupt a decryption AND it had valid
padding, you know what that padding byte is.

It is easy to get tripped up on the fact that CBC plaintexts are
"padded". Padding oracles have nothing to do with the actual padding
on a CBC plaintext. It's an attack that targets a specific bit of code
that handles decryption. You can mount a padding oracle on ANY CBC
block, whether it's padded or not.
"""
    strings = """
MDAwMDAwTm93IHRoYXQgdGhlIHBhcnR5IGlzIGp1bXBpbmc=
MDAwMDAxV2l0aCB0aGUgYmFzcyBraWNrZWQgaW4gYW5kIHRoZSBWZWdhJ3MgYXJlIHB1bXBpbic=
MDAwMDAyUXVpY2sgdG8gdGhlIHBvaW50LCB0byB0aGUgcG9pbnQsIG5vIGZha2luZw==
MDAwMDAzQ29va2luZyBNQydzIGxpa2UgYSBwb3VuZCBvZiBiYWNvbg==
MDAwMDA0QnVybmluZyAnZW0sIGlmIHlvdSBhaW4ndCBxdWljayBhbmQgbmltYmxl
MDAwMDA1SSBnbyBjcmF6eSB3aGVuIEkgaGVhciBhIGN5bWJhbA==
MDAwMDA2QW5kIGEgaGlnaCBoYXQgd2l0aCBhIHNvdXBlZCB1cCB0ZW1wbw==
MDAwMDA3SSdtIG9uIGEgcm9sbCwgaXQncyB0aW1lIHRvIGdvIHNvbG8=
MDAwMDA4b2xsaW4nIGluIG15IGZpdmUgcG9pbnQgb2g=
MDAwMDA5aXRoIG15IHJhZy10b3AgZG93biBzbyBteSBoYWlyIGNhbiBibG93
""".strip().split()

    def encrypt(key, data):
        iv = random_key(16)
        return iv, AES.new(key, IV=iv, mode=AES.MODE_CBC).encrypt(pkcs7_pad(16, data))

    def check_padding(key, iv, data):
        plain = AES.new(key, IV=iv, mode=AES.MODE_CBC).decrypt(data)
        try:
            pkcs7_strip(plain)
            return True
        except PadException:
            return False

    def decrypt(blocklen, fcheck, data):
        def decrypt_byte(block, known):
            ridx = len(known) + 1
            suffix = ''.join(chr(ord(x) ^ ridx) for x in known)
            attack = random_key(blocklen - ridx)
            for i in xrange(256):
                if fcheck(attack + chr(i) + suffix, block):
                    #TODO test for length of padding
                    return chr(ridx ^ i)

        plain = ''
        blocks = list(''.join(b) for b in grouper(blocklen, data))
        for prev, cur in pairwise(blocks):
            known = ''
            while len(known) < blocklen:
                known = decrypt_byte(cur, known) + known
            plain += xor_block(prev, known)
        return pkcs7_strip(plain)

    key = random_key(16)
    data = random.choice(strings).decode('base64')
    iv, ciphertext = encrypt(key, data)
    fcheck = partial(check_padding, key)
    plain = decrypt(16, fcheck, iv + ciphertext)
    print plain
    print 'Match' if data == plain else 'No Match'


def cc18():
    """18. Implement CTR mode

The string:

   L77na/nrFsKvynd6HzOoG7GHTLXsTVu9qvY/2syLXzhPweyyMTJULu/6/kXX0KSvoOLSFQ==

decrypts to something approximating English in CTR mode, which is an
AES block cipher mode that turns AES into a stream cipher, with the
following parameters:

         key=YELLOW SUBMARINE
         nonce=0
         format=64 bit unsigned little endian nonce,
                64 bit little endian block count (byte count / 16)

CTR mode is very simple.

Instead of encrypting the plaintext, CTR mode encrypts a running
counter, producing a 16 byte block of keystream, which is XOR'd
against the plaintext.

For instance, for the first 16 bytes of a message with these
parameters:

   keystream = AES("YELLOW SUBMARINE",
                   "\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00")

for the next 16 bytes:

   keystream = AES("YELLOW SUBMARINE",
                   "\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00")

and then:

   keystream = AES("YELLOW SUBMARINE",
                   "\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x00\x00\x00\x00\x00\x00")

CTR mode does not require padding; when you run out of plaintext, you
just stop XOR'ing keystream and stop generating keystream.

Decryption is identical to encryption. Generate the same keystream,
XOR, and recover the plaintext.

Decrypt the string at the top of this function, then use your CTR
function to encrypt and decrypt other things.
"""
    key = 'YELLOW SUBMARINE'
    data = 'L77na/nrFsKvynd6HzOoG7GHTLXsTVu9qvY/2syLXzhPweyyMTJULu/6/kXX0KSvoOLSFQ=='.decode('base64')
    print xor_aes_ctr(key, 0, data)


def cc19():
    """19. Break fixed-nonce CTR mode using substitions

Take your CTR encrypt/decrypt function and fix its nonce value to
0. Generate a random AES key.

In SUCCESSIVE ENCRYPTIONS (NOT in one big running CTR stream), encrypt
each line of the base64 decodes of the following,
producing multiple independent ciphertexts:

  SSBoYXZlIG1ldCB0aGVtIGF0IGNsb3NlIG9mIGRheQ==
  Q29taW5nIHdpdGggdml2aWQgZmFjZXM=
  RnJvbSBjb3VudGVyIG9yIGRlc2sgYW1vbmcgZ3JleQ==
  RWlnaHRlZW50aC1jZW50dXJ5IGhvdXNlcy4=
  SSBoYXZlIHBhc3NlZCB3aXRoIGEgbm9kIG9mIHRoZSBoZWFk
  T3IgcG9saXRlIG1lYW5pbmdsZXNzIHdvcmRzLA==
  T3IgaGF2ZSBsaW5nZXJlZCBhd2hpbGUgYW5kIHNhaWQ=
  UG9saXRlIG1lYW5pbmdsZXNzIHdvcmRzLA==
  QW5kIHRob3VnaHQgYmVmb3JlIEkgaGFkIGRvbmU=
  T2YgYSBtb2NraW5nIHRhbGUgb3IgYSBnaWJl
  VG8gcGxlYXNlIGEgY29tcGFuaW9u
  QXJvdW5kIHRoZSBmaXJlIGF0IHRoZSBjbHViLA==
  QmVpbmcgY2VydGFpbiB0aGF0IHRoZXkgYW5kIEk=
  QnV0IGxpdmVkIHdoZXJlIG1vdGxleSBpcyB3b3JuOg==
  QWxsIGNoYW5nZWQsIGNoYW5nZWQgdXR0ZXJseTo=
  QSB0ZXJyaWJsZSBiZWF1dHkgaXMgYm9ybi4=
  VGhhdCB3b21hbidzIGRheXMgd2VyZSBzcGVudA==
  SW4gaWdub3JhbnQgZ29vZCB3aWxsLA==
  SGVyIG5pZ2h0cyBpbiBhcmd1bWVudA==
  VW50aWwgaGVyIHZvaWNlIGdyZXcgc2hyaWxsLg==
  V2hhdCB2b2ljZSBtb3JlIHN3ZWV0IHRoYW4gaGVycw==
  V2hlbiB5b3VuZyBhbmQgYmVhdXRpZnVsLA==
  U2hlIHJvZGUgdG8gaGFycmllcnM/
  VGhpcyBtYW4gaGFkIGtlcHQgYSBzY2hvb2w=
  QW5kIHJvZGUgb3VyIHdpbmdlZCBob3JzZS4=
  VGhpcyBvdGhlciBoaXMgaGVscGVyIGFuZCBmcmllbmQ=
  V2FzIGNvbWluZyBpbnRvIGhpcyBmb3JjZTs=
  SGUgbWlnaHQgaGF2ZSB3b24gZmFtZSBpbiB0aGUgZW5kLA==
  U28gc2Vuc2l0aXZlIGhpcyBuYXR1cmUgc2VlbWVkLA==
  U28gZGFyaW5nIGFuZCBzd2VldCBoaXMgdGhvdWdodC4=
  VGhpcyBvdGhlciBtYW4gSSBoYWQgZHJlYW1lZA==
  QSBkcnVua2VuLCB2YWluLWdsb3Jpb3VzIGxvdXQu
  SGUgaGFkIGRvbmUgbW9zdCBiaXR0ZXIgd3Jvbmc=
  VG8gc29tZSB3aG8gYXJlIG5lYXIgbXkgaGVhcnQs
  WWV0IEkgbnVtYmVyIGhpbSBpbiB0aGUgc29uZzs=
  SGUsIHRvbywgaGFzIHJlc2lnbmVkIGhpcyBwYXJ0
  SW4gdGhlIGNhc3VhbCBjb21lZHk7
  SGUsIHRvbywgaGFzIGJlZW4gY2hhbmdlZCBpbiBoaXMgdHVybiw=
  VHJhbnNmb3JtZWQgdXR0ZXJseTo=
  QSB0ZXJyaWJsZSBiZWF1dHkgaXMgYm9ybi4=

(This should produce 40 short CTR-encrypted ciphertexts).

Because the CTR nonce wasn't randomized for each encryption, each
ciphertext has been encrypted against the same keystream. This is very
bad.

Understanding that, like most stream ciphers (including RC4, and
obviously any block cipher run in CTR mode), the actual "encryption"
of a byte of data boils down to a single XOR operation, it should be
plain that:

 CIPHERTEXT-BYTE XOR PLAINTEXT-BYTE = KEYSTREAM-BYTE

And since the keystream is the same for every ciphertext:

 CIPHERTEXT-BYTE XOR KEYSTREAM-BYTE = PLAINTEXT-BYTE (ie, "you don't
 say!")

Attack this cryptosystem "Carmen Sandiego" style: guess letters, use
expected English language frequence to validate guesses, catch common
English trigrams, and so on. Points for automating this, but part of
the reason I'm having you do this is that I think this approach is
suboptimal.
"""
    strings = [s.strip() for s in cc19.__doc__.splitlines()[9:49]]
    key = random_key(16)
    ciphertexts = [xor_aes_ctr(key, 0, s.decode('base64')) for s in strings]

    def test_keystream(keystream):
        for i,c in enumerate(ciphertexts):
            print '%s\t%s' % (i, xor_block(keystream, c[:len(keystream)]))

    def test_plain(keystream, idx, test, debug=False):
        c1 = ciphertexts[idx]
        tlen = len(test)

        idx_counts = defaultdict(int)
        for c2 in ciphertexts:
            output = ''
            for i in xrange(min(len(c1), len(c2))):
                key = xor_block(test, c1[i:i+tlen])
                plain = xor_block(key, c2[i:i+tlen])
                if all(c in ok for c in plain):
                    idx_counts[i] += 1
                else:
                    plain = ' ' * tlen
                output += '|' + plain
            if debug:
                print output
        key_idx = max((v,k) for k,v in idx_counts.iteritems())[1]
        newkeystream = keystream[:key_idx]
        newkeystream += xor_block(test, c1[key_idx:key_idx+tlen])
        newkeystream += keystream[key_idx+tlen:]
        return newkeystream

    keystream = '-' * max(len(c) for c in ciphertexts)

    print """
Look for 'the' in first line.  Got lucky, column of reasonable decodes means it's there.
Expand it to ' them ' by trial and error
"""
    keystream = test_plain(keystream, 0, ' them ', debug=True)

    print """
Guess 'meaningless' in line 5/7 and eventually expand it to ' meaningless words, '
"""
    keystream = test_plain(keystream, 7, ' meaningless words, ')
    test_keystream(keystream)

    print """
Bust out Google: 'meaningless words companion beautiful harriers'
Easter, 1916, huh?  That's pretty early for MTV.  Test the theory:
"""
    keystream = xor_block('He, too, has been changed in his turn,', ciphertexts[37])
    test_keystream(keystream)

    print
    print "Keystream:", keystream.encode('hex')
    print


def cc20():
    """20. Break fixed-nonce CTR mode using stream cipher analysis

At the following URL:

  https://gist.github.com/3336141

Find a similar set of Base64'd plaintext. Do with them exactly
what you did with the first, but solve the problem differently.

Instead of making spot guesses at to known plaintext, treat the
collection of ciphertexts the same way you would repeating-key
XOR.

Obviously, CTR encryption appears different from repeated-key XOR,
but with a fixed nonce they are effectively the same thing.

To exploit this: take your collection of ciphertexts and truncate
them to a common length (the length of the smallest ciphertext will
work).

Solve the resulting concatenation of ciphertexts as if for repeating-
key XOR, with a key size of the length of the ciphertext you XOR'd.
"""
    key = random_key(16)
    with open('data/cc20.txt') as f:
        ciphertexts = [xor_aes_ctr(key, 0, line.decode('base64')) for line in f]

    blocklen = min(len(c) for c in ciphertexts)

    #we can beat shortest (53 bytes) by extending blocklen till we don't have enough
    #data to recover the plaintext with our scoring function.  91 bytes in this case.
    #lengths = sorted(len(c) for c in ciphertexts)
    #blocklen = lengths[-20]

    blocks = [c[:blocklen] for c in ciphertexts if len(c) >= blocklen]
    blocks = [''.join(b) for b in zip(*blocks)]

    keys = [chr(x) for x in xrange(256)]

    keystream = []
    for block in blocks:
        best = score_decodings(keys, score_ratio, block)[0]
        keystream.append(best[1])

    keystream = ''.join(keystream)
    for block in (c[:blocklen] for c in ciphertexts):
        print xor_block(keystream, block)

    print
    print 'Block (min line) length:', blocklen
    print "Keystream: '%s'" % keystream.encode('hex')


def cc21():
    """21. Implement the MT19937 Mersenne Twister RNG

You can get the psuedocode for this from Wikipedia. If you're writing
in Python, Ruby, or (gah) PHP, your language is probably already
giving you MT19937 as "rand()"; don't use rand(). Write the RNG
yourself.
"""
    print "First 16 outputs with seed=1"
    rng = MersenneTwister(1)
    for i in xrange(16):
        print rng.rand()


def cc22():
    """22. "Crack" An MT19937 Seed

Make sure your MT19937 accepts an integer seed value. Test it (verify
that you're getting the same sequence of outputs given a seed).

Write a routine that performs the following operation:

* Wait a random number of seconds between, I don't know, 40 and 1000.

* Seeds the RNG with the current Unix timestamp

* Waits a random number of seconds again.

* Returns the first 32 bit output of the RNG.

You get the idea. Go get coffee while it runs. Or just simulate the
passage of time, although you're missing some of the fun of this
exercise if you do that.

From the 32 bit RNG output, discover the seed.
"""
    def get_number(minwait, maxwait, fast=False):
        tnow = int(time.time())
        wait = random.randint(minwait, maxwait)
        tnow += wait
        if not fast:
            time.sleep(wait)
        rng = MersenneTwister(tnow)
        wait = random.randint(minwait, maxwait)
        tnow += wait
        if not fast:
            time.sleep(wait)
        return tnow, rng.rand()

    tnow, output = get_number(40, 1000, fast=True)
    print 'Output:', output

    #find any seed in the last 10k seconds
    for seed in xrange(tnow, tnow - 10000, -1):
        if MersenneTwister(seed).rand() == output:
            print "Seed:", seed
            break


def cc23():
    """23. Clone An MT19937 RNG From Its Output

The internal state of MT19937 consists of 624 32 bit integers.

For each batch of 624 outputs, MT permutes that internal state. By
permuting state regularly, MT19937 achieves a period of 2**19937,
which is Big.

Each time MT19937 is tapped, an element of its internal state is
subjected to a tempering function that diffuses bits through the
result.

The tempering function is invertible; you can write an "untemper"
function that takes an MT19937 output and transforms it back into the
corresponding element of the MT19937 state array.

To invert the temper transform, apply the inverse of each of the
operations in the temper transform in reverse order. There are two
kinds of operations in the temper transform each applied twice; one is
an XOR against a right-shifted value, and the other is an XOR against
a left-shifted value AND'd with a magic number. So you'll need code to
invert the "right" and the "left" operation.

Once you have "untemper" working, create a new MT19937 generator, tap
it for 624 outputs, untemper each of them to recreate the state of the
generator, and splice that state into a new instance of the MT19937
generator.

The new "spliced" generator should predict the values of the original.

How would you modify MT19937 to make this attack hard? What would
happen if you subjected each tempered output to a cryptographic hash?
"""
    rshift = lambda val, n: (val % 0x100000000) >> n

    def invert_right(y, shiftlen):
        i = 0
        output = 0
        while i * shiftlen < 32:
            chunk = y & rshift(-1 << (32 - shiftlen), shiftlen * i)
            y ^= rshift(chunk, shiftlen)
            output |= chunk
            i += 1
        return output

    def invert_left(y, shiftlen, mask):
        i = 0
        output = 0
        while i * shiftlen < 32:
            chunk = y & rshift(-1, 32 - shiftlen) << (shiftlen * i)
            y ^= (chunk << shiftlen) & mask
            output |= chunk
            i += 1
        return output

    def untemper(y):
        y = invert_right(y, 18)
        y = invert_left(y, 15, 0xefc60000)
        y = invert_left(y, 7, 0x9d2c5680)
        y = invert_right(y, 11)
        return y


    rng1 = MersenneTwister(int(time.time()))
    MT = [untemper(rng1.rand()) for _ in xrange(624)]

    rng2 = MersenneTwister(0)
    rng2.MT = MT

    print 'Original\tClone'
    for _ in xrange(16):
        print '%s\t%s' % (rng1.rand(), rng2.rand())


def cc24():
    """24. Create the MT19937 Stream Cipher And Break It

You can create a trivial stream cipher out of any PRNG; use it to
generate a sequence of 8 bit outputs and call those outputs a
keystream. XOR each byte of plaintext with each successive byte of
keystream.

Write the function that does this for MT19937 using a 16-bit
seed. Verify that you can encrypt and decrypt properly. This code
should look similar to your CTR code.

Use your function to encrypt a known plaintext (say, 14 consecutive
'A' characters) prefixed by a random number of random characters.

From the ciphertext, recover the "key" (the 16 bit seed).

Use the same idea to generate a random "password reset token" using
MT19937 seeded from the current time.

Write a function to check if any given password token is actually
the product of an MT19937 PRNG seeded with the current time.
"""
    def xor_mt_ctr(seed, data):
        def gen_keystream():
            rng = MersenneTwister(seed)
            while True:
                for c in struct.pack('!I', rng.rand()):
                    yield c

        return ''.join(chr(ord(x) ^ ord(y)) for x,y in itertools.izip(data, gen_keystream()))

    #test xor_mt_ctr()
    seed = random.randint(0, 0xFFFFFFFF)
    ok = xor_mt_ctr(seed, xor_mt_ctr(seed, 'YELLOW SUBMARINE')) == 'YELLOW SUBMARINE'
    print "xor_mt_ctr(%s, xor_mt_ctr(%s, 'YELLOW SUBMARINE')) == 'YELLOW SUBMARINE': %s" % (seed, seed, ok)
    print

    def encrypt(seed, prefix, data):
        return xor_mt_ctr(seed, prefix + data)

    #generate a seed and use it to encrypt some random bytes + 'A' * 14
    seed = random.randint(0, 0xFFFF)
    print "Seed:", seed
    prefix = random_key(random.randint(1,32))
    ciphertext = encrypt(seed, prefix, 'A' * 14)

    #find the last chunk of ciphertext that aligns with a full int from the RNG
    blocklen = 4
    rounds = len(ciphertext) / blocklen
    ridx = len(ciphertext) % 4
    start = len(ciphertext) - (ridx + blocklen)
    end = len(ciphertext) - ridx
    key = struct.unpack('!I', xor_block(ciphertext[start:end], 'AAAA'))[0]

    #brute-force search all seeds to see which one matches key after 'rounds' rounds
    for seed in xrange(0, 0xFFFF + 1):
        rng = MersenneTwister(seed)
        for _ in xrange(rounds):
            r = rng.rand()
        if r == key:
            print 'Found seed:', seed
            print
            break

    def reset_token():
        return xor_mt_ctr(int(time.time()), 'YELLOW SUBMARINE').encode('hex')

    def check_reset(token, grace):
        tnow = int(time.time())
        token = token.decode('hex')
        for seed in xrange(tnow - grace, tnow + grace):
            if xor_mt_ctr(seed, token) == 'YELLOW SUBMARINE':
                return True
        return False

    print "Generate a token and check it with a grace period of +- 5 minutes"
    print "Good Token:"
    token = reset_token()
    print token, check_reset(token, 300)

    print "Bad Token:"
    token = random_key(16).encode('hex')
    print token, check_reset(token, 300)


if __name__ == '__main__':
    for f in (cc17, cc18, cc19, cc20, cc21, cc22, cc23, cc24):
        print f.__doc__.split('\n')[0]
        f()
        print

