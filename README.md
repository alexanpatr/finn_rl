# Project: End-to-End CNN Design Exploration using FINN

We provide instructions on how to run for model LeNet5. ResNets models are also supported. Models were tested on Alveo U250.

## Step 1: Install Dependencies

```
git clone https://github.com/joannapng/finn.git
cd finn
git checkout dev
```

## Step 2: Download project and add to FINN folder
```
git clone https://github.com/joannapng/finn_rl.git
```

## Step 3: Run finn docker container
```	
bash run-docker.sh
cd finn_rl
```

## Step 4: Pretrain LeNet5 on MNIST / ResNet18 on CIFAR10
```
python pretrain.py --model-name LeNet5 --dataset MNIST --training-epochs 10
python pretrain.py --model-name resnet18 --dataset CIFAR10 --training-epochs 30
```

## Step 5: Train agent on LeNet5
```
mkdir LeNet5
python train.py --model-name LeNet5 --dataset MNIST --model-path <path to model (should be inside checkpoints folder ending in _best.tar)> --freq 200 --target-fps 6000 --board U250 --num-episodes 30

mkdir resnet18
python train.py --model-name resnet18 --dataset CIFAR10 --model-path <path to model (should be inside checkpoints folder ending in _best.tar)> --freq 200 --target-fps 2500 --board U250 --num-episodes 200 # takes long, you can skip this step
```
## Step 6: Test agent on LeNet5
```
python test.py --model-name LeNet5 --dataset MNIST --model-path <path to model> --freq 200 --target-fps 6000 --output-dir LeNet5 --onnx-output LeNet5 --agent-path agents/agent_LeNet5 --board U250

python test.py --model-name resnet18 --dataset CIFAR10 --model-path <path to model> --freq 200 --target-fps 3000 --output-dir resnet18 --onnx-output resnet18 --board U250 --use-custom-strategy --strategy "[3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 4, 3, 3, 4, 3, 3, 3, 3, 3, 4, 3, 4, 3, 4, 4, 4, 4, 4, 4, 3, 4, 4, 4, 4, 4, 4, 4, 4, 4, 5, 5, 5, 5, 4, 5, 5, 4, 5, 7]" # use custom strategy (one that was provided from agent during training)
```

## Step 7: Export model to HW
```
python export.py --model-name LeNet5 --onnx-model LeNet5/LeNet5_quant.onnx --output-dir LeNet5 --input-file LeNet5/input.npy --expected-output-file LeNet5/expected_output.npy --folding-config-file LeNet5/folding_config.json --board U250 --synth-clk-period-ns 5.0

python export.py --model-name resnet18 --onnx-model resnet18/resnet18_quant.onnx --output-dir resnet18 --input-file resnet18/input.npy --expected-output-file resnet18/expected_output.npy --folding-config-file resnet18/folding_config.json --board U250 --synth-clk-period-ns 5.0
```

## Step 8: 
This project has not been tested with other models or platforms yet, but if you want to do so you have to add the model and the platform to the flow as so:

# How to add your model to the flow
1. Add your PyTorch model definition inside folder `pretrain/models` and update `pretrain/models/__init__.py`
2. Change lines 14-21 of `pretrain/trainer/Trainer.py` to include your model. Do the same with lines 16-24 of `train/finetune/Finetuner.py`
3. You must also add your custom streamlining and convert to hw function. Add those in files `train/export/Exporter.py` and `exporter/Exporter.py` following the format of `streamline_resnet` and `convert_to_hw_resnet`. Include then in the dictionary `streamline_functions` and `convert_to_hw_functions` of `exporter.py` and `train/env/ModelEnv.py`.

# How to add your platform to the flow
1. Add a `.json` file in the folder `platforms`. Make sure it follows the format of `platforms/U250.json`
2. Update the dictionary `platform_files` in `train/env/ModelEnv.py` and `train/exporter/Exporter.py`