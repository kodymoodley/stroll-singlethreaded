import torch
from sklearn.preprocessing import LabelEncoder
from transformers import BertTokenizer, BertModel
import fasttext
import numpy as np


UPOS = [
        '_', 'ADJ', 'ADP', 'ADV', 'AUX', 'CCONJ', 'DET', 'INTJ', 'NOUN',
        'NUM', 'PRON', 'PROPN', 'PUNCT', 'SCONJ', 'SYM', 'VERB', 'X'
        ]

XPOS = [
        '_', '1', '2', '2b', '2v', '3', '3m', '3o', '3p', '3v', 'aanw', 'ADJ',
        'adv-pron', 'afgebr', 'afk', 'agr', 'basis', 'bep', 'betr', 'bez',
        'bijz', 'BW', 'comp', 'conj', 'dat', 'deeleigen', 'det', 'dim',
        'eigen', 'enof', 'ev', 'evf', 'evmo', 'evon', 'evz', 'excl', 'fem',
        'fin', 'gen', 'genus', 'getal', 'grad', 'hoofd', 'inf', 'init',
        'LET', 'LID', 'masc', 'meta', 'met-e', 'met-s', 'met-t', 'mv',
        'mv-n', 'N', 'nadr', 'neven', 'nom', 'nomin', 'obl', 'od', 'onbep',
        'onder', 'onz', 'pers', 'persoon', 'postnom', 'pr', 'prenom',
        'pron', 'pv', 'rang', 'recip', 'red', 'refl', 'rest', 'rest3',
        'soort', 'SPEC', 'stan', 'sup', 'symb', 'tgw', 'TSW', 'TW', 'vb',
        'vd', 'verl', 'versm', 'VG', 'VNW', 'vol', 'vreemd', 'vrij', 'VZ',
        'WW', 'zijd', 'zonder', 'zonder-n'
        ]

DEPREL = [
        '_', 'acl', 'acl:relcl', 'advcl', 'advmod', 'amod', 'appos',
        'aux', 'aux:pass', 'case', 'cc', 'ccomp', 'compound:prt', 'conj',
        'cop', 'csubj', 'det', 'expl', 'expl:pv', 'fixed', 'flat', 'iobj',
        'mark', 'nmod', 'nmod:poss', 'nsubj', 'nsubj:pass', 'nummod', 'obj',
        'obl', 'obl:agent', 'orphan', 'parataxis', 'punct', 'root', 'xcomp'
        ]

FEATS = [
        '_', 'Abbr=Yes', 'Case=Acc', 'Case=Dat', 'Case=Gen', 'Case=Nom',
        'Definite=Def', 'Definite=Ind', 'Degree=Cmp', 'Degree=Pos',
        'Degree=Sup', 'Foreign=Yes', 'Gender=Com', 'Gender=Com,Neut',
        'Gender=Neut', 'Number=Plur', 'Number=Sing', 'Person=1', 'Person=2',
        'Person=3', 'PronType=Dem', 'PronType=Ind', 'PronType=Int',
        'PronType=Prs', 'PronType=Rcp', 'PronType=Rel', 'Reflex=Yes',
        'Tense=Past', 'Tense=Pres', 'VerbForm=Fin', 'VerbForm=Inf',
        'VerbForm=Part'
        ]

ROLES = [
        '_',
        'Arg0', 'Arg1', 'Arg2', 'Arg3', 'Arg4', 'Arg5', 'ArgM-ADV', 'ArgM-CAU',
        'ArgM-DIR', 'ArgM-DIS', 'ArgM-EXT', 'ArgM-LOC', 'ArgM-MNR', 'ArgM-MOD',
        'ArgM-NEG', 'ArgM-PNC', 'ArgM-PRD', 'ArgM-REC', 'ArgM-STR', 'ArgM-TMP'
        ]

# ROLE_WEIGHTS = [
#     1e-4,
#     2.0, 2.0, 2.0, 2.0, 2.0, 2.0,
#     0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5
#     ]
ROLE_WEIGHTS = [
    0.1,
    2.5, 1.5, 75, 750, 750, 750,
    10., 25., 75., 10., 50., 10., 10., 10., 25., 25., 50., 50., 5., 5.
    ]

FRAMES = ['_', 'rel']
FRAME_WEIGHTS = [1.0, 10.0]

upos_codec = LabelEncoder().fit(UPOS)
xpos_codec = LabelEncoder().fit(XPOS)
deprel_codec = LabelEncoder().fit(DEPREL)
feats_codec = LabelEncoder().fit(FEATS)
frame_codec = LabelEncoder().fit(FRAMES)
role_codec = LabelEncoder().fit(ROLES)


def encoded_weights(codec, labels, weights):
    """Label weights are defined in the same order as we define the labels.
    However, the LabelEncoder reorders the labels.
    This function applys the same reordering to the weights."""
    idx = codec.transform(labels)
    return torch.Tensor([weights[i] for i in idx])


encoded_frame_weights = encoded_weights(frame_codec, FRAMES, FRAME_WEIGHTS)
encoded_role_weights = encoded_weights(role_codec, ROLES, ROLE_WEIGHTS)


def to_one_hot(codec, values):
    if type(values) == type([]):
        value_idxs = codec.transform(values)
        return torch.eye(len(codec.classes_))[value_idxs].sum(axis=0)
    else:
        value_idxs = codec.transform([values])
        return torch.eye(len(codec.classes_))[value_idxs].flatten()


def to_index(codec, values):
    return torch.tensor(codec.transform([values])).flatten()


class FasttextEncoder:
    """Use Fasttext word vectors per word"""
    def __init__(self, filename):
        self.model = fasttext.load_model(filename)
        self.dims = self.model.get_dimension()
        self.name = 'FT{}'.format(self.dims)

    def __call__(self, sentence):
        word_vectors = []
        for token in sentence:
            word_vectors.append(torch.Tensor(self.model[token.FORM]))

        return word_vectors


class BertEncoder:
    """Use averaged bert vectors over constituent tokens"""
    def __init__(self):
        self.tokenizer = BertTokenizer.from_pretrained("bert-base-dutch-cased")
        self.model = BertModel.from_pretrained("bert-base-dutch-cased")
        self.model.eval()
        self.dims = 768
        self.name = 'BERT'

    def __call__(self, sentence):
        self.model.eval()

        # Tokenize input
        # TODO: [CLS] and [SEP] symbols?
        tokenized_text = self.tokenizer.tokenize(sentence.full_text)

        # Convert token to vocabulary indices
        indexed_tokens = self.tokenizer.convert_tokens_to_ids(tokenized_text)

        # Convert inputs to PyTorch tensors
        tokens_tensor = torch.tensor([indexed_tokens])

        with torch.no_grad():
            # torch tensor of shape
            # (batch_size=1, sequence_length, hidden_size=768)
            bert_output, _ = self.model(tokens_tensor)

        # Realign the tokens and build the word vectors by averaging
        # ['Repareer',             'de', 'token-izatie',                   ]
        # ['Rep', '##are', '##er', 'de', 'to', '##ken', '-', 'iza', '##tie']
        word_vectors = []

        # Align tokenizations
        #  * BERT can break up our 'gold' tokens in smaller parts
        #  * BERT does not merge any of our white-space separated tokens
        bert_i = 0
        # loop over the gold tokens
        for gold_i, gold_t in enumerate(sentence):
            chars_gold = len(gold_t.FORM)
            chars_bert = 0
            subword_tensors = []

            # keep adding BERT tokens until they make up the gold token
            while chars_bert < chars_gold and bert_i < len(tokenized_text):
                subword_tensors.append(bert_output[0, bert_i])

                bert_t = tokenized_text[bert_i]
                if bert_t == self.tokenizer.unk_token:
                    # assume the unk token stands for the whole remaining gold
                    # token
                    chars_bert = chars_gold
                else:
                    chars_bert = chars_bert + len(bert_t)
                    if bert_t[0:2] == '##':
                        chars_bert = chars_bert - 2

                bert_i = bert_i + 1

            # average and append to OUtput
            try:
                word_vectors.append(
                        torch.mean(torch.stack(subword_tensors, dim=1), 1)
                        )
            except:
                # print (sentence)
                # print ('len subword_tensors', len(subword_tensors))
                # print (bert_i, chars_bert, gold_i, chars_gold, gold_t)
                word_vectors.append(torch.zeros([self.dims]))

        return word_vectors
