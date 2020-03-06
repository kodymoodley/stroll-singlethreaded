import time
import signal

import torch
import torch.nn.functional as F

from torch.utils.data import DataLoader
from torch.utils.tensorboard import SummaryWriter

import dgl
import dgl.function as fn

from stroll.graph import GraphDataset, draw_graph
from stroll.model import Net
from stroll.labels import BertEncoder, FRAME_WEIGHTS, ROLE_WEIGHTS, frame_codec, role_codec

import matplotlib.pyplot as plt
import seaborn as sns

import logging
logging.basicConfig(level=logging.WARNING)

torch.manual_seed(43)

# Not used at the moment
# device = 'cuda' if torch.cuda.is_available() else 'cpu'

# https://docs.dgl.ai/tutorials/models/1_gnn/1_gcn.html
# https://towardsdatascience.com/understanding-pytorch-with-an-example-a-step-by-step-tutorial-81fc5f8c4e8e
# https://towardsdatascience.com/building-efficient-custom-datasets-in-pytorch-2563b946fd9f


if __name__ == '__main__':
    logging.info('Initializing sentence encoder')
    sentence_encoder = BertEncoder()
    #sentence_encoder = None

    batch_size = 50
    learning_rate = 1e-2
    h_dims = 64
    features = ['UPOS', 'FEATS', 'DEPREL', 'WVEC']
    exp_name = 'runs/tanhshrink_mean_{}_ae_'.format(h_dims) + '_'.join(features)
    exp_name += '{:1.0e}_{:d}'.format(learning_rate, batch_size)

    train_set = GraphDataset('train.conllu', sentence_encoder=sentence_encoder, features=features)
    test_set = GraphDataset('quick.conllu', sentence_encoder=sentence_encoder, features=features)

    logging.info('Building test graph')
    test_graph = dgl.batch([g for g in test_set])

    # Create network
    # out_feats:
    # ROLE := 21
    # FRAME := 2
    logging.info('Building model')
    net = Net(in_feats=train_set.in_feats, h_dims=h_dims, out_feats_a=2, out_feats_b=21)
    print(net)

    def sigterm_handler(_signo, _stack_frame):
        print('Aborting')
        writer.close()
        torch.save(net.state_dict(), './model.pt')
        exit(0)

    signal.signal(signal.SIGTERM, sigterm_handler)
    signal.signal(signal.SIGINT, sigterm_handler)


    # Training settings
    #  * mini batch size of 50 sentences
    #  * shuffle the data on each epochs
    #  * Adam with fixed learning rate fo 1e-3
    trainloader = DataLoader(train_set, batch_size=batch_size, shuffle=True, collate_fn=dgl.batch)
    optimizer = torch.optim.Adam(net.parameters(), lr=learning_rate)
    #  * 2 epochs
    num_epochs = 20

    # Log settings
    writer = SummaryWriter(exp_name)

    # diagnostic settings
    word_count = 0
    count_per_eval = 5000
    next_eval = count_per_eval
    t0 = time.time()

    logging.info('Start training')
    # loop over the epochs
    for epoch in range(num_epochs):
        # loop over each minibatch
        for g in trainloader:
            net.train()

            # inputs (minibatch, C, d_1, d_2, ..., d_K)
            # target (minibatch,    d_1, d_2, ..., d_K)
            # minibatch = minibatch Size
            # C         = number of classes
            # d_x       = extra dimensions
            logits_frame, logits_role = net(g)

            target = g.ndata['frame']
            logits_frame = logits_frame.transpose(0,1)
            loss_frame = F.cross_entropy(
                    logits_frame.view(1,2,-1),
                    target.view(1,-1),
                    FRAME_WEIGHTS.view(1,-1))

            target = g.ndata['role']
            logits_role = logits_role.transpose(0,1)
            loss_role = F.cross_entropy(
                    logits_role.view(1,21,-1),
                    target.view(1,-1),
                    ROLE_WEIGHTS.view(1,-1))

            # add the two losses
            loss = 10. * loss_role + loss_frame

            # apply loss
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            # diagnostics
            word_count = word_count + len(g)

            if word_count > next_eval:
                dur = time.time() - t0
                acc1, acc2, conf1, conf2 = net.evaluate(test_graph)
                print("Elements {:08d} | LossA {:.4f} | LossB {:.4f} | Acc1 {:.4f} | Acc2 {:.4f} | words/sec {:4.3f}".format(
                        word_count, loss_role.item(), loss_frame.item(), acc1, acc2, len(g) / dur
                        )
                     )

                figure = plt.figure(figsize=[10., 10.])
                labels = frame_codec.classes_
                fmt=".0f"
                sns.heatmap(conf1, fmt=fmt, annot=True, cbar=False, cmap="Greens", xticklabels=labels, yticklabels=labels)
                writer.add_figure('confusion_matrix-Frame', figure, word_count)

                figure = plt.figure(figsize=[10., 10.])
                labels = role_codec.classes_
                sns.heatmap(conf2, fmt=fmt, annot=True, cbar=False, cmap="Greens", xticklabels=labels, yticklabels=labels)
                writer.add_figure('confusion_matrix-Role', figure, word_count)

                writer.add_scalar('loss_frame', loss_frame.item(), word_count)
                writer.add_scalar('loss_role', loss_role.item(), word_count)
                writer.add_scalar('loss_total', loss.item(), word_count)
                writer.add_scalar('accuracy_frame', acc1, word_count)
                writer.add_scalar('accuracy_role', acc2, word_count)

                for name, param in net.state_dict().items():
                     writer.add_histogram('hist_' + name, param, word_count)
                     writer.add_scalar('norm_' + name, torch.norm(param), word_count)

                # reset timer
                next_eval = next_eval + count_per_eval
                t0 = time.time()

        print ('Epoch {} done'.format(epoch))
        torch.save(net.state_dict(), './model_{}.pt'.format(epoch))

    torch.save(net.state_dict(), './model.pt')
    writer.close()
