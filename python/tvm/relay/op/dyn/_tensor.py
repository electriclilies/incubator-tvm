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
#pylint: disable=invalid-name, unused-argument, len-as-condition
"""Backend compiler related feature registration for dynamic ops"""

from ..op import register_shape_func
from .._tensor import full_shape_func

register_shape_func("dyn.broadcast_to", True, full_shape_func)
register_shape_func("dyn.ones", True, no_data_full_shape_func)
register_shape_func("dyn.zeros", True, no_data_full_shape_func)
