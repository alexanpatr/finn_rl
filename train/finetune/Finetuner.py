import torch
import torchvision
import torch.nn as nn
import torch.nn.functional as F
import uuid
import os
import copy

import sys
sys.path.append(".")

from torch.utils.data import DataLoader, sampler, random_split
from torchvision import transforms
from torchvision.datasets import CIFAR10, MNIST
import torchvision.models
#from pretrain.utils import get_torchvision_model
from .validate import validate
from .calibrate import calibrate
from pretrain.models.LeNet5 import LeNet5
from pretrain.models.resnet import ResNet18, ResNet34, ResNet50, ResNet101, ResNet152

networks = {'LeNet5' : LeNet5,
			'resnet18' : ResNet18, 
			'resnet34' : ResNet34,
			'resnet50' : ResNet50,
			'resnet101' : ResNet101,
			'resnet152' : ResNet152}

class Finetuner(object):
	def __init__(self, args, model_config):
		self.args = args
		
		# Initialize device
		self.device = None
		self.init_device()

		# Initialize dataset
		self.train_set = None
		self.test_loader = None
		self.num_classes = None
		self.in_channels = None
		self.batch_size_finetuning = self.args.batch_size_finetuning
		self.batch_size_testing = self.args.batch_size_testing

		self.init_dataset(self.args, model_config)

		self.finetuning_epochs = self.args.finetuning_epochs

		# Initialize model
		self.init_model()

		# Initialize optimizer
		self.finetuning_optimizer = None
		self.init_finetuning_optim()

		# Initialize loss function
		self.criterion = None
		self.init_loss()

	def init_device(self):
		if self.args.device == 'GPU' and torch.cuda.is_available():
			print('Using GPU device')
			self.device = 'cuda'
		else:
			print('Using CPU device')
			self.device = 'cpu'

	def init_dataset(self, args, config):
		if args.dataset == 'CIFAR10':
			normalize = transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010))

			builder = CIFAR10
			self.num_classes = 10
			self.in_channels = 3

			transformations = transforms.Compose([
				transforms.RandomCrop(32, padding = 4),
				transforms.RandomHorizontalFlip(),
				transforms.ToTensor(),
				normalize
			])
		elif args.dataset == 'MNIST':
			normalize = transforms.Normalize(mean = (0.1307, ), std = (0.3081, ))

			builder = MNIST
			self.num_classes = 10
			self.in_channels = 1
		
			transformations = transforms.Compose([
				transforms.Resize(28),
				transforms.CenterCrop(28),
				transforms.ToTensor(),
				normalize
			])
		else:
			# for imagenet
			transformations = transforms.Compose([
					transforms.Resize(config['resize_shape']),
					transforms.CenterCrop(config['center_crop_shape']),
					transforms.ToTensor(),
					normalize
				])
		
		self.train_set = builder(root=args.datadir,
							train=True,
							download=True,
							transform=transformations)
		
		self.test_set = builder(root=args.datadir,
						   train=False,
						   download=True,
						   transform=transformations)

		total_length = len(self.train_set)
		calib_length = int(args.calib_subset * total_length)

		train_length = total_length - calib_length

		self.train_set, self.calib_set = random_split(
			self.train_set, 
			[train_length, calib_length]
		)

		self.train_set, _ = random_split(self.train_set, 
										 [int(train_length * self.args.finetuning_subset), 
										  int(train_length - train_length * self.args.finetuning_subset)])

		self.train_loader = DataLoader(self.train_set,
									   batch_size = self.batch_size_finetuning,
									   num_workers = self.args.num_workers,
									   shuffle = True)
		
		self.calib_loader = DataLoader(self.calib_set, 
									   batch_size = self.batch_size_finetuning,
									   num_workers = self.args.num_workers,
									   shuffle = True)
			 
		self.test_loader = DataLoader(self.test_set,
									  batch_size = self.batch_size_testing,
									  num_workers = self.args.num_workers)
		
	def init_model(self):
		builder = networks[self.args.model_name]
		self.model = builder(num_classes = self.num_classes, in_channels = self.in_channels).to(self.device)

		print('Loading model from {}'.format(self.args.model_path))

		self.orig_acc = None
		package = torch.load(self.args.model_path, map_location = self.device)
		self.model.load_state_dict(package['state_dict'])
		
		self.model.to(self.device)
		self.orig_acc = package['best_val_acc']

	def init_finetuning_optim(self):

		self.finetuning_lr = self.args.finetuning_lr
		
		if self.args.optimizer == 'Adam':
			self.finetuning_optimizer = torch.optim.Adam(self.model.parameters(), lr = self.finetuning_lr, weight_decay = self.args.weight_decay)
		elif self.args.optimizer == 'SGD':
			self.finetuning_optimizer = torch.optim.SGD(self.model.parameters(), lr = self.finetuning_lr, 
													  weight_decay = self.args.weight_decay, momentum=self.args.momentum)
		
		self.starting_epoch = 0
		
	def init_loss(self):
		if self.args.loss == 'CrossEntropy':
			self.criterion = nn.CrossEntropyLoss()
		elif self.args.loss == 'SqrHinge':
			self.criterion = nn.SqrHingeLoss()
	
	def check_accuracy(self, loader, model, eval = True):
		num_correct = 0
		num_samples = 0
		if eval:
			model.eval() # set model to evaluation mode

		with torch.no_grad():
			for x_val, y_val in loader:
				x_val = x_val.to(self.device)
				y_val = y_val.to(self.device)
				scores = model(x_val)
				_, preds = scores.max(1)
				num_correct += (preds == y_val).sum()
				num_samples += preds.size(0)
			acc = float(num_correct) / num_samples
			print('Got {} / {} correct ({})'.format(num_correct, num_samples, 100 * acc))
		
		return acc

	def finetune(self):
			num_steps = len(self.train_loader)
			for epoch in range(self.starting_epoch, self.finetuning_epochs):
				self.model.train()
				self.criterion.train()

				for i, (x_train, y_train) in enumerate(self.train_loader):
					x_train = x_train.to(self.device)
					y_train = y_train.to(self.device)

					scores = self.model(x_train)
					loss = self.criterion(scores, y_train)

					self.finetuning_optimizer.zero_grad()
					loss.backward()
					self.finetuning_optimizer.step()

					if i % self.args.print_every == 0:
						print("Epoch: [{}/{}], Step: [{}/{}], Loss: {:.4f}"
							.format(epoch, self.finetuning_epochs, i, num_steps, loss))

			#print("Training Complete")
			# Testing accuracy in the testing dataset
			print('-------- Testing Accuracy -------')
			self.test_acc = self.check_accuracy(self.test_loader, self.model, eval = False)
			return 0.0, self.model
	
	def validate(self, eval = True):
		return validate(self.model, val_loader=self.test_loader, eval = eval)

	def calibrate(self):
		calibrate(self.args, self.model, calib_loader=self.calib_loader)
		
	