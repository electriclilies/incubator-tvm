
import tvm
from tvm import relay
from tvm.contrib import graph_runtime

import numpy as np
import copy

class Calibrater:
    # calibration_map is a map from relay scale and zero point variables to subgraphs. 
    # it is one of the outputs of the quantize pass. see the documentation of that pass
    # for more details
    def __init__(self, quantized_mod, calibration_map, params=None):
        self.calibration_map = calibration_map
        self.quantized_mod = quantized_mod
        self.params = params

        self.var_map = {} # map of variables to final output

    # For an op in the original graph with 2 inputs, var_pairs is a 3d tuple of the form 
    # (((input1_scale, input1_zp), (input2_scale, input2_zp))).
    # The corresponding input_subgraph_pairs are 
    # (((input1_data_fn, input1_quantized_data_fn), (input2_data_fn, input2_quantized_data_fn)))
    # where input1_data_fn is the original, unquantized version of input1 in runnable function form, and
    # input1_quantized_data_fn is the quantized version of input1 in runnable function form. 
    # The output_subgraph_pair is (output_data_fn, output_quantized_data_fn)
    # output_data_fn is the original, unquantized version of the operation in runnable function form, and
    # output_quantized_data_fn is the dequantized output of the quantized operation
    # You will need to pass scales and zero points to output_quantized_data_fn for all the scales and zero points
    # corresponding to this node (ie, all the scale and zero point variables in var_pairs)
    def calibration_callback(self, var_pairs, input_subgraph_fn_pairs, output_subgraph_fn_pair):
        raise NotImplementedError

    # helper function to determine whether input is a weight
    def is_weight(self, expr):
        pass
    
    # bind variable name in subgraph to value (allows user to bind variable multiple times in a subgraph)
    def bind_variable(self, subgraph_fn, name, value):
        # TODO: do we have to make subgraph into a mod?
        return relay.build_module.bind_params_by_name(subgraph_fn, {name : value})
    
    # assume previous scale, zp are already bound in subgraph
    # runs the subgraph_fn passing in inputs as the inputs to the module
    def evaluate_subgraph(self, subgraph_fn, inputs):
        # TODO: add constant folding..
        with tvm.transform.PassContext(opt_level=3, disabled_pass=["AlterOpLayout"]):
            lib = relay.build(subgraph_fn, 'llvm', self.params)
        module = graph_runtime.GraphModule(lib["default"](tvm.cpu())) # TODO: make the target easy to change
        module.set_input(**inputs)
        
        if self.params:
            module.set_input(**self.params)

        module.run()

        # subgraph only has one output # TODO: double check this is true
        return module.get_output(0).asnumpy()

    def calibrate(self):
        for (variable_pairs), (input_subgraph_pairs, output_subgraph_pair) in self.calibration_map.items():
            
            """
            for ((scale_var, zp_var), (subgraph_fn, quantized_subgraph_fn)) in zip(variable_pairs, subgraph_pairs):
                # bind previously set scale and zp in quantized subgraph function
                quantized_subgraph_fn = relay.build_module.bind_params_by_name(quantized_subgraph_fn, self.var_map)

                scale_name = scale_var.name_hint
                zp_name = zp_var.name_hint
                (scale_value, zp_value) = self.calibration_callback(scale_name, zp_name, subgraph_fn, quantized_subgraph_fn)

                self.var_map[scale_name] = np.array(scale_value).astype('float32')
                self.var_map[zp_name] = np.array(zp_value).astype('int32')
            """
            value_pairs = self.calibration_callback(variable_pairs, input_subgraph_pairs, output_subgraph_pair)
            for ((scale_var, zp_var), (scale_value, zp_value)) in zip(variable_pairs, value_pairs):
                scale_name = scale_var.name_hint
                zp_name = zp_var.name_hint
                self.var_map[scale_name] = scale_value
                self.var_map[zp_name] = zp_value

        # TODO: change me to create a new mod. 
        calibrated_func = relay.build_module.bind_params_by_name(self.quantized_mod['main'], self.var_map)
        # TODO: HOW OT EXPLICITLY CONSTRUCT A MOD WITH A NAMED FUNCTION
        calibrated_mod = copy.deepcopy(self.quantized_mod)
        calibrated_mod['main'] = calibrated_func

        optimize = tvm.transform.Sequential(
            [relay.transform.FoldConstant()])
        with relay.build_config(opt_level=3, disabled_pass=["AlterOpLayout"]):
            print("constant folding")
            calibrated_mod = optimize(calibrated_mod)
            print("done")
        
        print("calibrated mod")
        print(calibrated_mod)
        print("_____________")
        return calibrated_mod