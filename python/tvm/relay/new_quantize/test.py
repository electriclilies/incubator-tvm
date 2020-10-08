import tvm
import onnx
import torch
from torchvision.models import resnet
from tvm import relay
import quantize_pass
import global_calibration_pass
import numpy as np
from tvm.relay.testing import ctx_list

# ONNX TEST
"""
onnx_model = onnx.load('resnet18-v1-7.onnx')
input_dict = {'data': [1, 3, 224, 224]}
mod, params = relay.frontend.from_onnx(onnx_model, input_dict)
mod = quantize_pass.quantize(mod, params)

print("ONNX resnet 18 quantized with our quantize pass:")
print(mod['main'])
"""

pytorch_model = resnet.resnet18(pretrained=True)
input_name = "input"  # the input name can be be arbitrary for PyTorch frontend.
input_shape = (1, 3, 224, 224)
named_input_shape = [(input_name, input_shape)]
input_data = torch.randn(input_shape)
script_module = torch.jit.trace(pytorch_model, input_data)

input_shapes = [(input_name, (1, 3, 224, 224))]
mod, params = relay.frontend.from_pytorch(script_module, named_input_shape)
quantized_mod, calibration_map = quantize_pass.quantize(mod, params) # Maybe this should return a mod..

calibration_var_vals = global_calibration_pass.global_calibrate(calibration_map, 1.2, 1)

input_np = np.random.randn(1, 3, 224, 224).astype('float32')

inputs = calibration_var_vals

quantized_mod['main'] = relay.build_module.bind_params_by_name(quantized_mod['main'], inputs)

with tvm.transform.PassContext(opt_level=3):
    lib = relay.build(quantized_mod, target='llvm')

from tvm.contrib import graph_runtime
gmod = graph_runtime.GraphModule(lib["default"](tvm.cpu()))
gmod.set_input('input', input_np)
gmod.run()
out = gmod.get_output(0).asnumpy()
print(out)


# TODO: consider using a Let instead of FN args for defining calibration variables. Will allow easier constant folding, etc.
# Will need to think about how the UI works. 




#print(calibration_map.keys())
# we can't run infer type on gmod??

"""
first_scale, first_zp = list(calibration_map.keys())[0]
print(first_scale)
print(first_zp)

orig_expr, q_expr = calibration_map[(first_scale, first_zp)]

input_np = np.random.randn(1, 3, 224, 224).astype('float32')
with relay.build_config(opt_level=0):
    grt = relay.build(tvm.ir.IRModule.from_expr(orig_expr), target='llvm')

from tvm.contrib import graph_runtime
gmod = graph_runtime.GraphModule(grt["default"](tvm.cpu()))
print(gmod.get_input(0))
exit()
gmod.set_input('input', input_np)
gmod.set_input(**params)
gmod.run()
out = gmod.get_output(0).asnumpy()
print(out)
"""