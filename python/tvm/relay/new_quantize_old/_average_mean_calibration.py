import tvm
from tvm import relay
from tvm.relay.new_quantize import Calibrater, quantize_pass

import onnx

import tensorflow.compat.v2 as tf
import tensorflow_datasets as tfds
tf.enable_v2_behavior()

import numpy as np

batch_size = 5

class DatasetManager():
    def __init__(self):
        raise NotImplementedError

    def get_next_batch(self):
        raise NotImplementedError

    def num_batches(self):
        raise NotImplementedError

    def is_empty(self):
        raise NotImplementedError

    def reset(self):
        raise NotImplementedError

class TFDatasetManager(DatasetManager):
    def __init__(self, tf_dataset, batch_size, num_batches):
        self.idx = 0
        self.n_batches = num_batches
        self.batch_size = batch_size
        self.tf_dataset = tf_dataset
        self.tf_iter = iter(self.tf_dataset)
    
    # Returns the next batch of data
    def get_next_batch(self):
        if (self.idx >= self.n_batches):
            raise IndexError
        self.idx += 1
        
        data, label = next(self.tf_iter)
        return data.numpy(), label.numpy()
    
    def num_batches(self):
        return self.n_batches

    def is_empty(self):
        return self.idx >= self.n_batches

    def reset(self):
        self.tf_iter = iter(self.tf_dataset)
        self.idx = 0

class AverageMeanCalibrater(Calibrater):
    def __init__(self, dataset_manager):
        super().__init__()
        self.dataset_manager = dataset_manager

    def calibration_callback(self, var_pairs, input_subgraph_fn_pairs, output_subgraph_fn_pair):
        value_dict = {}
        for ((scale_var, zp_var), (data_subgraph_fn, quantized_data_subgraph_fn)) in zip(var_pairs, input_subgraph_fn_pairs):            
            # Calculate the average min, max across each batch
            min_sum = 0
            max_sum = 0
            while not self.dataset_manager.is_empty():
                image, _ = self.dataset_manager.get_next_batch()
                
                out = self.evaluate_subgraph(data_subgraph_fn, {'flatten_input': image})

                min_sum += np.min(out)
                max_sum += np.max(out)

            self.dataset_manager.reset()

            avg_min = min_sum / self.dataset_manager.num_batches() 
            avg_max = max_sum / self.dataset_manager.num_batches() 

            # Determine the threshold for quantization
            threshold = np.mean([np.abs(avg_min), np.abs(avg_max)])
            # Since this is a symmetric distribution and we are quantizing to int8, there are 256 bins, and 128 are positive
            scale = threshold / 128
            value_dict[scale_var.name_hint] = np.array(scale).astype('float32')
            value_dict[zp_var.name_hint] = np.array(0).astype('int32')
        return value_dict

# TFDS loading from https://www.tensorflow.org/datasets/keras_example
(ds_train, ds_test), ds_info = tfds.load('mnist',
                                         split=['train', 'test'],
                                         shuffle_files=True,
                                         as_supervised=True,
                                         with_info=True)

# Import data
def normalize_img(image, label):
  """Normalizes images: `uint8` -> `float32`."""
  return tf.cast(image, tf.float32) / 255., label

ds_train = ds_train.map(
    normalize_img, num_parallel_calls=tf.data.experimental.AUTOTUNE)
ds_train = ds_train.cache()
ds_train = ds_train.shuffle(ds_info.splits['train'].num_examples)
ds_train = ds_train.batch(batch_size)
ds_train = ds_train.prefetch(tf.data.experimental.AUTOTUNE)

ds_test = ds_test.map(
    normalize_img, num_parallel_calls=tf.data.experimental.AUTOTUNE)
ds_test = ds_test.batch(batch_size)
ds_test = ds_test.cache()
ds_test = ds_test.prefetch(tf.data.experimental.AUTOTUNE)

num_batches = 2000
mnist_train_manager = TFDatasetManager(ds_train, batch_size, 12000)
mnist_test_manager = TFDatasetManager(ds_test, batch_size, 2000)

# Import onnx model, quantize and calibrate
onnx_model = onnx.load('/home/lorthsmith/tvm/python/tvm/relay/new_quantize/mnist_model.onnx')
input_dict = {'flatten_input': [batch_size, 28, 28, 1]}
mod, params = relay.frontend.from_onnx(onnx_model, input_dict)
print("Unquantized mod: ")
print(mod.astext(False))
print(" ____________________________ ")

quantized_mod, calibration_map = quantize_pass.quantize(mod, params=params, target='llvm', ctx=tvm.cpu(), skip_layers=[1])
print("Quantized mod: ")
print(quantized_mod.astext(False))

#average_mean_calibrater = AverageMeanCalibrater(mnist_train_manager)
#calibrated_mod = average_mean_calibrater.calibrate(quantized_mod, calibration_map)

with tvm.transform.PassContext(opt_level=3, disabled_pass=["AlterOpLayout"]):
    q_lib = relay.build(quantized_mod, target='llvm')
    lib = relay.build(mod, target='llvm')
exit()
from tvm.contrib import graph_runtime
q_gmod = graph_runtime.GraphModule(q_lib["default"](tvm.cpu()))
gmod = graph_runtime.GraphModule(lib["default"](tvm.cpu()))
q_correct = 0
correct = 0
total = 0

while not mnist_train_manager.is_empty():
    image, label = mnist_train_manager.get_next_batch()
    q_gmod.set_input(**{'flatten_input': image})
    q_gmod.run()
    q_out = q_gmod.get_output(0).asnumpy()

    gmod.set_input(**{'flatten_input': image})
    gmod.run()
    out = gmod.get_output(0).asnumpy()

    q_predicted_labels = np.argmax(q_out, axis=1)
    predicted_labels = np.argmax(out, axis=1)

    print("Int8 labels: ", q_predicted_labels)
    print("Float32 labels: ", predicted_labels)
    print("Actual labels: ", label)

    q_correct += np.sum(q_predicted_labels == label)
    correct += np.sum(predicted_labels == label)
    total += batch_size

print("Int8 percent correct: ", (q_correct / total) * 100)
print("Float32 percent correct: ", (correct / total) * 100)
print("Difference: ", (((correct / total) * 100) - ((q_correct / total) * 100)))