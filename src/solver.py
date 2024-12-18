# Created on 2018/12
# Author: Kaituo XU

import os
import time

import torch
import numpy as np
import matplotlib.pyplot as plt

from pit_criterion import cal_loss


class Solver(object):
    
    def __init__(self, data, model, optimizer, args):
        self.tr_loader = data['tr_loader']
        self.cv_loader = data['cv_loader']
        self.model = model
        self.optimizer = optimizer

        # Training config
        self.use_cuda = args.use_cuda
        self.epochs = args.epochs
        self.half_lr = args.half_lr
        self.early_stop = args.early_stop
        self.max_norm = args.max_norm
        # save and load model
        self.save_folder = args.save_folder
        self.checkpoint = args.checkpoint
        self.continue_from = args.continue_from
        self.model_path = args.model_path
        # logging
        self.print_freq = args.print_freq
        # visualizing loss using visdom
        self.tr_loss = torch.Tensor(self.epochs)
        self.cv_loss = torch.Tensor(self.epochs)
        self.visdom = args.visdom
        self.visdom_epoch = args.visdom_epoch
        self.visdom_id = args.visdom_id
        if self.visdom:
            from visdom import Visdom
            self.vis = Visdom(env=self.visdom_id)
            self.vis_opts = dict(title=self.visdom_id,
                                 ylabel='Loss', xlabel='Epoch',
                                 legend=['train loss', 'cv loss'])
            self.vis_window = None
            self.vis_epochs = torch.arange(1, self.epochs + 1)

        self.model_repeats = args.R
        self.model_blocks = args.X
        self.epoch_weights = []
        self.all_epoch_weights = []
        self.iter_weights={}
    
        self._reset()

    def _reset(self):
        # Reset
        if self.continue_from:
            print('Loading checkpoint model %s' % self.continue_from)
            package = torch.load(self.continue_from)
            self.model.module.load_state_dict(package['state_dict'])
            self.optimizer.load_state_dict(package['optim_dict'])
            self.start_epoch = int(package.get('epoch', 1))
            self.tr_loss[:self.start_epoch] = package['tr_loss'][:self.start_epoch]
            self.cv_loss[:self.start_epoch] = package['cv_loss'][:self.start_epoch]
        else:
            self.start_epoch = 0
        # Create save folder
        os.makedirs(self.save_folder, exist_ok=True)
        self.prev_val_loss = float("inf")
        self.best_val_loss = float("inf")
        self.halving = False
        self.val_no_impv = 0

    def get_weights(self):
        lst_weights = []
        # p_relu_str_1 = "module.separator.network.2.{}.{}.net.1.weight"
        # p_relu_str_2 = "module.separator.network.2.{}.{}.net.3.net.1.weight"
        #
        # # p_relu_str_1 = "module.separator.network.2.{}.{}.net.0.weight"
        # # p_relu_str_2 = "module.separator.network.2.{}.{}.net.3.net.0.weight"
        # global_1 = "module.separator.network.2.{}.{}.net.2.gamma"
        # global_2 = "module.separator.network.2.{}.{}.net.3.net.2.gamma"
        st_dict = self.model.state_dict()
        print(self.model.state_dict().keys())
        # for r in range(self.model_repeats):
        #     for x in range(self.model_blocks):
        #         temp = p_relu_str_1.format(r, x)
        #         lst_weights[(r, x, "act1")] = st_dict[temp]
        #         # print(f"is this workin? {temp} {st_dict[temp]}")
        #         temp = p_relu_str_2.format(r, x)
        #         lst_weights[(r, x, "act2")] = st_dict[temp]
        #         temp = global_1.format(r, x)
        #         lst_weights[(r, x, "global1")] = st_dict[temp]
        #         temp = global_2.format(r, x)
        #         lst_weights[(r, x, "global2")] = st_dict[temp]
        # # print(f'heyy {lst_weights}')

        lst_conv_layers = ["module.separator.network.2.{}.{}.net.0.weight",
                           "module.separator.network.2.{}.{}.net.2.gamma",
                           "module.separator.network.2.{}.{}.net.2.beta",
                           "module.separator.network.2.{}.{}.net.3.net.0.weight",
                           "module.separator.network.2.{}.{}.net.3.net.2.gamma",
                           "module.separator.network.2.{}.{}.net.3.net.2.beta",
                           "module.separator.network.2.{}.{}.net.3.net.3.weight"]
        st_dict = self.model.state_dict()
        for r in range(self.model_repeats):
            for x in range(self.model_blocks):
                for layer in lst_conv_layers:
                    temp = layer.format(r, x)
                    lst_weights.append(st_dict[temp])
                # temp = p_relu_str_1.format(r, x)
        return lst_weights

    def graph_densities(self):
        # print(self.epoch_weights[0][5].size())

        flat_weights = []
        flat_count = 0
        dead_count = 0
        for i in range(len(self.all_epoch_weights[0])):
            flat_tensor = self.all_epoch_weights[0][i].reshape(-1)
            for value in flat_tensor:
                # flat_weights.append(value)
                flat_count += 1
                if value<=0.01 and value >= -0.01:
                    dead_count += 1

        print("Total: ",flat_count)
        print("Dead: ",dead_count)

        # downsampled = np.random.choice(flat_weights, size=np.floor(len(flat_weights)/10000))
        # #
        # ranges = np.arange(0,1,0.1)
        # plt.figure()
        # plt.hist(downsampled, bins=ranges)
        # plt.xlabel("Value Range")
        # plt.ylabel("Frequency")
        # plt.xticks(ranges)
        # plt.savefig(self.save_folder + "/value_density.pdf", format="pdf", bbox_inches="tight")

    def get_model_avgs(self, iter):
        model_avg = self.get_avg_weights()
        self.iter_weights[iter] = (sum(model_avg.values()) / len(model_avg))

    def get_avg_weights(self):
        lst_weights = {}
        # p_relu_str_1 = "module.separator.network.2.{}.{}.net.1.weight"
        # p_relu_str_2 = "module.separator.network.2.{}.{}.net.3.net.1.weight"
        lst_conv_layers = ["module.separator.network.2.{}.{}.net.0.weight",
                           "module.separator.network.2.{}.{}.net.2.gamma",
                           "module.separator.network.2.{}.{}.net.2.beta",
                           "module.separator.network.2.{}.{}.net.3.net.0.weight",
                           "module.separator.network.2.{}.{}.net.3.net.2.gamma",
                           "module.separator.network.2.{}.{}.net.3.net.2.beta",
                           "module.separator.network.2.{}.{}.net.3.net.3.weight"]
        st_dict = self.model.state_dict()
        for r in range(self.model_repeats):
            for x in range(self.model_blocks):
                for layer in lst_conv_layers:
                    temp = layer.format(r, x)
                    lst_weights[f"{r} {x} glb2"] = torch.mean(st_dict[temp]).item()
                # temp = p_relu_str_1.format(r, x)
                # # lst_weights[(r, x, "act1")] = torch.mean(st_dict[temp]).item()
                # lst_weights[f"{r} {x} act1"] = torch.mean(st_dict[temp]).item()
                # print(f"is this workin? {temp} {st_dict[temp]}")
                # temp = global_1.format(r, x)
                # # lst_weights[(r, x, "global1")] = torch.mean(st_dict[temp]).item()
                # lst_weights[f"{r} {x} glb1"] = torch.mean(st_dict[temp]).item()
                # # temp = p_relu_str_2.format(r, x)
                # # # lst_weights[(r, x, "act2")] = torch.mean(st_dict[temp]).item()
                # # lst_weights[f"{r} {x} act2"] = torch.mean(st_dict[temp]).item()
                # temp = global_2.format(r, x)
                # # lst_weights[(r, x, "global2")] = torch.mean(st_dict[temp]).item()
                # lst_weights[f"{r} {x} glb2"] = torch.mean(st_dict[temp]).item()
        # print(f'heyy {lst_weights}')
        return lst_weights
    
    def graph_epoch_weights(self):
        print(self.epoch_weights)
        graph_data = self.epoch_weights
        plt.figure()
        if len(self.epoch_weights) == 1:
            graph_data = self.epoch_weights[0]
            plt.plot(graph_data.keys(), graph_data.values(), marker='o')
            plt.xlabel('Layers')
            plt.ylabel('Weights')
            plt.grid()
            plt.savefig(self.save_folder + "/epoch_plot.pdf", format="pdf", bbox_inches="tight")

    def graph_iter_weights(self):
        print("iter here!!")
        print(self.iter_weights)
        plt.figure()
        graph_data = self.iter_weights
        print(f'wah {list(graph_data.keys())}')
        plt.plot(graph_data.keys(), graph_data.values())
        plt.xlabel('Iterations')
        plt.ylabel('Weights')
        plt.grid()
        plt.savefig(self.save_folder + "/iter_plot.pdf", format="pdf", bbox_inches="tight")

    def train(self):
        # Train model multi-epoches
        for epoch in range(self.start_epoch, self.epochs):
            # Train one epoch
            print("Training...")
            self.model.train()  # Turn on BatchNorm & Dropout
            start = time.time()
            tr_avg_loss = self._run_one_epoch(epoch)
            print('-' * 85)
            print('Train Summary | End of Epoch {0} | Time {1:.2f}s | '
                  'Train Loss {2:.3f}'.format(
                      epoch + 1, time.time() - start, tr_avg_loss))
            print('-' * 85)

            # Save weights after each epoch
            self.all_epoch_weights.append(self.get_weights())
            self.epoch_weights.append(self.get_avg_weights())

            weights_path = file_path = os.path.join(
                self.save_folder, 'epoch%dweights.pth.tar' % (epoch + 1))
            # torch.save(self.model.module.serialize(self.epoch_weights), weights_path)
            self.graph_densities();
        
            # Save model each epoch
            if self.checkpoint:
                file_path = os.path.join(
                    self.save_folder, 'epoch%d.pth.tar' % (epoch + 1))
                torch.save(self.model.module.serialize(self.model.module,
                                                       self.optimizer, epoch + 1,
                                                       tr_loss=self.tr_loss,
                                                       cv_loss=self.cv_loss),
                           file_path)
                print('Saving checkpoint model to %s' % file_path)

            # Cross validation
            print('Cross validation...')
            self.model.eval()  # Turn off Batchnorm & Dropout
            val_loss = self._run_one_epoch(epoch, cross_valid=True)
            print('-' * 85)
            print('Valid Summary | End of Epoch {0} | Time {1:.2f}s | '
                  'Valid Loss {2:.3f}'.format(
                      epoch + 1, time.time() - start, val_loss))
            print('-' * 85)

            # Adjust learning rate (halving)
            if self.half_lr:
                if val_loss >= self.prev_val_loss:
                    self.val_no_impv += 1
                    if self.val_no_impv >= 3:
                        self.halving = True
                    if self.val_no_impv >= 10 and self.early_stop:
                        print("No imporvement for 10 epochs, early stopping.")
                        break
                else:
                    self.val_no_impv = 0
            if self.halving:
                optim_state = self.optimizer.state_dict()
                optim_state['param_groups'][0]['lr'] = \
                    optim_state['param_groups'][0]['lr'] / 2.0
                self.optimizer.load_state_dict(optim_state)
                print('Learning rate adjusted to: {lr:.6f}'.format(
                    lr=optim_state['param_groups'][0]['lr']))
                self.halving = False
            self.prev_val_loss = val_loss

            # Save the best model
            self.tr_loss[epoch] = tr_avg_loss
            self.cv_loss[epoch] = val_loss
            if val_loss < self.best_val_loss:
                self.best_val_loss = val_loss
                file_path = os.path.join(self.save_folder, self.model_path)
                torch.save(self.model.module.serialize(self.model.module,
                                                       self.optimizer, epoch + 1,
                                                       tr_loss=self.tr_loss,
                                                       cv_loss=self.cv_loss),
                           file_path)
                print("Find better validated model, saving to %s" % file_path)

            # visualizing loss using visdom
            if self.visdom:
                x_axis = self.vis_epochs[0:epoch + 1]
                y_axis = torch.stack(
                    (self.tr_loss[0:epoch + 1], self.cv_loss[0:epoch + 1]), dim=1)
                if self.vis_window is None:
                    self.vis_window = self.vis.line(
                        X=x_axis,
                        Y=y_axis,
                        opts=self.vis_opts,
                    )
                else:
                    self.vis.line(
                        X=x_axis.unsqueeze(0).expand(y_axis.size(
                            1), x_axis.size(0)).transpose(0, 1),  # Visdom fix
                        Y=y_axis,
                        win=self.vis_window,
                        update='replace',
                    )



    def _run_one_epoch(self, epoch, cross_valid=False):
        start = time.time()
        total_loss = 0

        data_loader = self.tr_loader if not cross_valid else self.cv_loader

        # visualizing loss using visdom
        if self.visdom_epoch and not cross_valid:
            vis_opts_epoch = dict(title=self.visdom_id + " epoch " + str(epoch),
                                  ylabel='Loss', xlabel='Epoch')
            vis_window_epoch = None
            vis_iters = torch.arange(1, len(data_loader) + 1)
            vis_iters_loss = torch.Tensor(len(data_loader))

        for i, (data) in enumerate(data_loader):
            padded_mixture, mixture_lengths, padded_source = data
            if self.use_cuda:
                padded_mixture = padded_mixture.cuda()
                mixture_lengths = mixture_lengths.cuda()
                padded_source = padded_source.cuda()
            estimate_source = self.model(padded_mixture)
            loss, max_snr, estimate_source, reorder_estimate_source = \
                cal_loss(padded_source, estimate_source, mixture_lengths)
            if not cross_valid:
                self.optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(),
                                               self.max_norm)
                self.optimizer.step()

            total_loss += loss.item()

            if i % self.print_freq == 0:
                print('Epoch {0} | Iter {1} | Average Loss {2:.3f} | '
                      'Current Loss {3:.6f} | {4:.1f} ms/batch'.format(
                          epoch + 1, i + 1, total_loss / (i + 1),
                          loss.item(), 1000 * (time.time() - start) / (i + 1)),
                      flush=True)

            if i % 100 == 0:
                self.get_model_avgs(i + 1)

            # visualizing loss using visdom
            if self.visdom_epoch and not cross_valid:
                vis_iters_loss[i] = loss.item()
                if i % self.print_freq == 0:
                    x_axis = vis_iters[:i+1]
                    y_axis = vis_iters_loss[:i+1]
                    if vis_window_epoch is None:
                        vis_window_epoch = self.vis.line(X=x_axis, Y=y_axis,
                                                         opts=vis_opts_epoch)
                    else:
                        self.vis.line(X=x_axis, Y=y_axis, win=vis_window_epoch,
                                      update='replace')

        self.graph_iter_weights()
        return total_loss / (i + 1)


