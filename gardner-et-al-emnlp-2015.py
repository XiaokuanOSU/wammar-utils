import subprocess
import gzip
import re
import time
import io
import sys
import argparse
from collections import defaultdict
import scipy
from scipy.sparse import coo_matrix
from scipy.io import savemat, loadmat
from math import log

# parse/validate arguments
argparser = argparse.ArgumentParser()
argparser.add_argument("-c", "--corpus", required=True, help="(input) multilingual corpus")
argparser.add_argument("-a", "--alignments", required= True, help="(input) alignments probabilities")
argparser.add_argument("-f", "--min_frequency", type=int, default=5, help="(hyperparameter) minimum frequency for a word to be included in the vocabulary")
argparser.add_argument("-w", "--window", type=int, default=3, help="(hyperparameter) distance between two cooccuring words in a sentence")
argparser.add_argument("-e", "--embeddings", required=True, help="(output) embeddings file")
args = argparser.parse_args()

# compute word frequencies
tokens_counter = 0
word2freq = defaultdict(float)
with io.open(args.corpus, encoding='utf8') as corpus:
  for line in corpus:
    tokens = line.strip().split(' ')
    for token in tokens:
      word2freq[token] += 1
      tokens_counter += 1
print 'corpus has', tokens_counter, 'tokens, and', len(word2freq), 'word types'

# filter out low frequency words from the vocabulary, and give each word a unique id
id2word = []
word2id = {}
id2freq = []
total_freq = 0
for word in word2freq.keys():
  freq = word2freq[word] * 1.0
  if freq < args.min_frequency: 
    del word2freq[word]
    continue
  word_id = len(id2word)
  word2id[word] = word_id
  id2word.append(word)
  freq *= args.window * 2.0
  id2freq.append(freq)
  total_freq += freq
  del word2freq[word]
# add sentence boundary words
SOS, EOS = u'<s>', u'</s>'
if SOS not in word2id:
  word2id[SOS] = len(id2word)
  id2word.append(SOS)
  id2freq.append(0.0)
if EOS not in word2id:
  word2id[EOS] = len(id2word)
  id2word.append(EOS)
  id2freq.append(0.0)
SOS_ID, EOS_ID = word2id[SOS], word2id[EOS]
print 'after excluding infrequent words, vocabulary size =', len(id2word)
assert len(id2freq) == len(id2word)

def write_x(word2context2freq, lang, any_any2freq, id2freq, id2word):
  # create three lists that summarize the data: row_ids, column_ids, pmis
  row_ids, column_ids, pmis = [], [], []
  for row_id in xrange(len(word2context2freq)):
    if not id2word[row_id][:2] == lang: continue
    row_freq = id2freq[row_id] * 1.0
    for column_id, joint_freq in word2context2freq[row_id].iteritems():
      column_freq = id2freq[column_id]
      assert(joint_freq != 0 and row_freq != 0 and column_freq != 0)
      pmi = log(joint_freq * any_any2freq / row_freq / column_freq)
      row_ids.append(row_id)
      column_ids.append(column_id)
      pmis.append(pmi)
    word2context2freq[row_id].clear()
  print 'done creating the lists row_ids, column_ids, pmis for COO matrix'

  # create the sparse matrix
  X = coo_matrix((pmis, (row_ids, column_ids)), shape=(len(id2word), len(id2word)))
  # we no longer need the lists
  pmis, row_ids, column_ids = None, None, None

  # save X in matlab format
  savemat('multilingual.X.{}.mat'.format(lang), dict(X=X))
  print 'wrote the matrix X to multilingual.X.{}.mat'.format(lang)
  X = None

# compute cooccurence statistics
word2context2freq = [defaultdict(float) for i in xrange(len(id2word))]
any_any2freq = total_freq
window_offsets = range(-args.window, 0) + range(1, args.window+1)
sys.stdout.write('lines processed:\n')
current_lang = ''
with io.open(args.corpus, encoding='utf8') as corpus:
  lines_counter = 0
  for line in corpus:
    lines_counter += 1
    if lines_counter % 100000 == 0: sys.stdout.write('{}\n'.format(lines_counter))
    if line[0:2] != current_lang:
      if current_lang != '': 
        write_x(word2context2freq, current_lang, any_any2freq, id2freq, id2word)
        # reset memory
        word2context2freq = None
        word2context2freq = [defaultdict(float) for i in xrange(len(id2word))]
      current_lang = line[0:2]
    id2freq[SOS_ID] += 2.0 * args.window
    id2freq[EOS_ID] += 2.0 * args.window
    # read a sentence
    splits = line.strip().split(' ')
    word_ids = []
    # first, insert SOS tokens
    for i in xrange(args.window):
      word_ids.append(SOS_ID)
    # then add frequent words
    for token in splits:
      if token not in word2id: continue
      word_ids.append(word2id[token])
    # then add EOS tokens
    for i in xrange(args.window):
      word_ids.append(EOS_ID)
    # update word_context2freq
    for token_index in xrange(args.window, len(word_ids) - args.window):
      focus_word_id = word_ids[token_index]
      for context_offset in window_offsets:
        context_word_id = word_ids[token_index + context_offset]
        word2context2freq[focus_word_id][context_word_id] += 1

  # write the matrix for the last language
  write_x(word2context2freq, current_lang, any_any2freq, id2freq, id2word)
print 'done counting in word2context2freq!!!'

# we no longer need the dictionary
word2context2freq = None

# save the word ids to interpret rows and columns of the matrix
with io.open('multilingual.vocab', encoding='utf8', mode='w') as vocab:
  for i in xrange(len(id2word)):
    vocab.write(u'{} {}\n'.format(i, id2word[i]))

# read alignment probabilities
src_ids, tgt_ids, probs = [], [], []
srcid2total = [0.0 for i in xrange(len(id2word))]
print 'file=',args.alignments
with io.open(args.alignments, encoding='utf8', mode='r') as alignments:
  for line in alignments:
    src, tgt, prob = line.strip().split(' ')
    prob = float(prob)
    # skip tiny probabilities
    if prob < 0.001: continue
    # skip infrequent words
    if src not in word2id or tgt not in word2id: continue
    # update the lists which will be later used to initialize a sparse scipy matrix
    src_id, tgt_id = word2id[src], word2id[tgt]
    # forward direction
    src_ids.append(src_id)
    tgt_ids.append(tgt_id)
    probs.append(prob)
    srcid2total[src_id] += prob
# normalize
for i in xrange(len(src_ids)):
  src_id = src_ids[i]
  probs[i] /= srcid2total[src_id]
print 'number of nonzero alignment probabilities in the {}x{} translation matrix is {}'.format(len(id2word), len(id2word), len(probs))

# create the sparse matrix that represents translations
print len(probs), len(src_ids), len(tgt_ids)
print probs[:10], src_ids[:10], tgt_ids[:10]
print probs[-10:], src_ids[-10:], tgt_ids[-10:]
D1 = coo_matrix((probs, (src_ids, tgt_ids)), shape=(len(id2word), len(id2word)))
# we no longer need the lists
probs, src_ids, tgt_ids = None, None, None

# save matrices in matlab format
savemat('multilingual.D.mat', dict(D=D1))
print 'wrote the matrix D1 to multilingual.mat'

# optimize using matlab. this function writes the output to files: DXDsvd40lam1.mat and timing.mat
subprocess.call(['matlab -nosplash -nodisplay -r "DXDsvd()"'], shell=True)

# now read the matrix Us from the output file DXDsvd40lam1.mat
outputs = loadmat('DXDsvd40lam1.mat')
Us = outputs['Us']
print 'Us.shape =', Us.shape

# read the vocabulary
id2word = []
with io.open('multilingual.vocab', encoding='utf8') as vocab:
  for line in vocab:
    word_id, word = line.strip().split(' ')
    assert int(word_id) == len(id2word)
    id2word.append(word)
print 'read {} words'.format(len(id2word))

# write the embeddings file
print 'embedding of id2word[0]=', id2word[0], 'is Us[0,:] =', Us[0,:].tolist()
with io.open(args.embeddings, encoding='utf8', mode='w') as embeddings_file:
  for i in xrange(len(id2word)):
    embedding = Us[i,:].tolist()
    embeddings_file.write(id2word[i])
    for j in xrange(len(embedding)):
      embeddings_file.write(u' {}'.format(embedding[j]))
    embeddings_file.write(u'\n')
