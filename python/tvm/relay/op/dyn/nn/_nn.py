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
# pylint: disable=no-else-return, invalid-name, unused-argument, too-many-arguments, consider-using-in
"""Backend compiler related feature registration"""
from __future__ import absolute_import

# upsampling
@reg.register_compute("dyn.nn.upsampling")
def compute_upsampling(attrs, inputs, out_dtype):
    data = inputs[0]
    scale_h = inputs[1]
    scale_w = inputs[2]
    layout = attrs.layout
    method = attrs.method
    align_corners = attrs.align_corners
    return [topi.nn.upsampling(data, scale_h, scale_w, layout, method, align_corners)]

reg.register_injective_schedule("dyn.nn.upsampling")


#####################
#  Shape functions  #
#####################

@script
def _upsampling_shape_func(dshape, scale_h, scale_w, layout):
    assert len(dshape.shape) == 1 and dshape.shape[0] == 4
    out = output_tensor((4,), "int64") # dshape is 4d
    if(layout == kNCHW("NCHW")): #how do i check what layout it is
        batch_size = dshape[0]
        channels = dshape[1]
        in_height = dshape[2]
        in_width = dshape[3]

        out[0] = batch_size
        out[1] = channels
        out[2] = in_height * scale_h
        out[3] = in_width * scale_w

        return out

    if (layout == kNHWC):
        batch_size = dshape[0]
        in_height = dshape[1]
        in_width = dshape[2]
        channels = dshape[3]

        out[0] = batch_size
        out[1] = in_height * h_scale
        out[2] = in_width * w_scale
        out[3] = channels

        return out

def upsampling_shape_func(attrs, inputs, _):
    return [_upsampling_shape_func(inputs[0], inputs[1], inputs[2], attrs.layout)]