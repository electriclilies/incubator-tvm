# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

import tvm
from tvm import relay
from tvm.relay.transform.quantize import Conv2DBiasAddPattern, partition_outputs, skip_partitions, rewrite_partitions, lower_partitions, QuantizerPattern
from typing import List
import numpy as np
from tvm.contrib import graph_runtime

class Quantizer():
    def __init__(self, func, params, patterns: List[QuantizerPattern], skip_first=True, skip_last=True):
        self.patterns = patterns
        self.original_func = prerequisite_optimize(func, params)

        # num_original outputs is -1 if output is not a Tuple, else is length of tuple
        if (isinstance(self.original_func.body, tvm.relay.expr.Tuple)):
            self.num_original_outputs = len(self.original_func.body)
        else:
            self.num_original_outputs = -1
        
        # Partition the func into sub functions containing the patterns we want to quantize
        partitioned_func = self.original_func
        for q_pattern in self.patterns:
            partitioned_func = q_pattern.pattern.partition(partitioned_func)

        # Get rid of first and last par
        partitioned_func = skip_partitions(partitioned_func, skip_first, skip_last)
        # Add outputs necessary for calibration
        tuple_subgraph_func = partition_outputs(partitioned_func)

        # Lower partitioned funcs and store in a mod
        self.tuple_subgraph_func = lower_partitions(tuple_subgraph_func)

        # Rewrite the multi-output graph to be quantized, and lower partitioned funcs
        outs = rewrite_partitions(self.patterns, tuple_subgraph_func)
        q_tuple_subgraph_func = outs['new_out']

        # Information about each partition used for calibration
        self.partition_infos = outs['infos_']

        # Lower quantized partitions and store in a mod        
        self.q_tuple_subgraph_func = lower_partitions(q_tuple_subgraph_func)

        # Create a function containing 
        quantized_func = self.q_tuple_subgraph_func
        if self.num_original_outputs == -1:
            self.quantized_func = relay.Function(self.q_tuple_subgraph_func.params, quantized_func.body.fields[0])
        else:
            self.quantized_func = relay.Function(self.q_tuple_subgraph_func.params, relay.Tuple(quantized_func.body.fields[self.num_original_outputs]))


def prerequisite_optimize(func, params=None):
    """ Prerequisite optimization passes for quantization. Perform
    "SimplifyInference", "FoldScaleAxis", "FoldConstant", and
    "CanonicalizeOps" optimization before quantization. """
    optimize = tvm.transform.Sequential(
        [relay.transform.DynamicToStatic(),
         relay.transform.SimplifyInference(),
         relay.transform.FoldConstant(),
         relay.transform.FoldScaleAxis()])#,
         #relay.transform.CanonicalizeOps(),
         #relay.transform.FoldConstant()])

    if params is not None:
        func = relay.build_module.bind_params_by_name(func, params)

    mod = tvm.ir.IRModule.from_expr(func)
    with relay.build_config(opt_level=3, disabled_pass=['AlterOpLayout']): # AlterOpLayout inserts pads and other ops in weird places
        mod = optimize(mod)

    return mod['main']