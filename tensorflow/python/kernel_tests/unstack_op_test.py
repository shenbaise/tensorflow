# Copyright 2015 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Functional tests for Unstack Op."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
from six.moves import xrange  # pylint: disable=redefined-builtin

from tensorflow.python.framework import constant_op
from tensorflow.python.framework import test_util
from tensorflow.python.ops import array_ops
from tensorflow.python.ops import gradient_checker
from tensorflow.python.platform import test


def np_split_squeeze(array, axis):
  axis_len = array.shape[axis]
  return [
      np.squeeze(
          arr, axis=(axis,)) for arr in np.split(
              array, axis_len, axis=axis)
  ]


class UnstackOpTest(test.TestCase):

  def randn(self, shape, dtype):
    data = np.random.randn(*shape)
    if dtype == np.bool:
      return data < 0  # Naive casting yields True with P(1)!
    else:
      return data.astype(dtype)

  def unstackReference(self, data, axis):
    """Use numpy primitives to implement unstack equivalent."""
    result = []
    rank = len(data.shape)
    axis = axis + rank if axis < 0 else axis
    for k in range(data.shape[axis]):
      axis = rank + axis if axis < 0 else axis
      # Slice in axis dimension of k'th slice.
      # e.g. if rank=4 k=2, axis=2 then equivalent of data[:,:,2,:]
      # Give error with loop context
      slice_spec = tuple(
          slice(None) if i != axis else k for i in range(rank))
      result.append(data.__getitem__(slice_spec))
    return result

  def testSimple(self):
    np.random.seed(7)
    for shape in (2,), (3,), (2, 3), (3, 2), (4, 3, 2):
      rank = len(shape)
      for axis in range(-rank, rank):
        for dtype in [
            np.bool, np.float16, np.float32, np.float64, np.uint8, np.int32,
            np.int64
        ]:
          data = self.randn(shape, dtype)
          # Convert data to a single tensorflow tensor
          x = constant_op.constant(data)

          # Unstack into a list of tensors
          ref = self.unstackReference(data, axis)
          cs = array_ops.unstack(x, axis=axis)
          self.assertEqual(type(cs), list)
          self.assertEqual(len(cs), shape[axis])
          for k, c in enumerate(cs):
            with self.subTest(shape=shape, k=k, axis=axis, dtype=dtype):
              self.assertAllEqual(ref[k], self.evaluate(c))

  def testSimpleGpu(self):
    if not test_util.is_gpu_available():
      self.skipTest('No GPU available')

    np.random.seed(7)
    with test_util.force_gpu():
      for shape in (2,), (3,), (2, 3), (3, 2), (4, 3, 2):
        rank = len(shape)
        for axis in range(-rank, rank):
          for dtype in [
              np.bool, np.float16, np.float32, np.float64, np.uint8, np.int32,
              np.int64
          ]:
            data = self.randn(shape, dtype)
            # Convert data to a single tensorflow tensor
            x = constant_op.constant(data)
            # Unstack into a list of tensors
            ref = self.unstackReference(data, axis)
            cs = array_ops.unstack(x, axis=axis)
            self.assertEqual(type(cs), list)
            self.assertEqual(len(cs), shape[axis])
            for k, c in enumerate(cs):
              # Give error with loop context
              with self.subTest(shape=shape, k=k, axis=axis, dtype=dtype):
                self.assertAllEqual(ref[k], self.evaluate(c))

  @test_util.run_deprecated_v1
  def testGradientsAxis0(self):
    for shape in (2,), (3,), (2, 3), (3, 2), (4, 3, 2):
      data = np.random.randn(*shape)
      shapes = [shape[1:]] * shape[0]
      for i in xrange(shape[0]):
        with self.cached_session():
          x = constant_op.constant(data)
          cs = array_ops.unstack(x, num=shape[0])
          err = gradient_checker.compute_gradient_error(x, shape, cs[i],
                                                        shapes[i])
          self.assertLess(err, 1e-6)

  @test_util.run_deprecated_v1
  def testGradientsAxis1(self):
    for shape in (2, 3), (3, 2), (4, 3, 2):
      data = np.random.randn(*shape)
      out_shape = list(shape)
      del out_shape[1]
      for i in xrange(shape[1]):
        with self.cached_session():
          x = constant_op.constant(data)
          cs = array_ops.unstack(x, num=shape[1], axis=1)
          err = gradient_checker.compute_gradient_error(x, shape, cs[i],
                                                        out_shape)
          self.assertLess(err, 1e-6)

  @test_util.run_deprecated_v1
  def testInferNum(self):
    for shape in (2,), (3,), (2, 3), (3, 2), (4, 3, 2):
      x = array_ops.placeholder(np.float32, shape=shape)
      cs = array_ops.unstack(x)
      self.assertEqual(type(cs), list)
      self.assertEqual(len(cs), shape[0])

  @test_util.run_deprecated_v1
  def testCannotInferNumFromUnknownShape(self):
    x = array_ops.placeholder(np.float32)
    with self.assertRaisesRegex(ValueError,
                                r'Cannot infer num from shape <unknown>'):
      array_ops.unstack(x)

  @test_util.run_deprecated_v1
  def testUnknownShapeOkWithNum(self):
    x = array_ops.placeholder(np.float32)
    array_ops.unstack(x, num=2)

  @test_util.run_deprecated_v1
  def testCannotInferNumFromNoneShape(self):
    x = array_ops.placeholder(np.float32, shape=(None,))
    with self.assertRaisesRegex(ValueError,
                                r'Cannot infer num from shape \((\?|None),\)'):
      array_ops.unstack(x)

  def testAgainstNumpy(self):
    # For 1 to 5 dimensions.
    for i in range(1, 6):
      a = np.random.random(np.random.permutation(i) + 1)

      # For all the possible axis to split it, including negative indices.
      for j in range(-i, i):
        expected = np_split_squeeze(a, j)

        actual_unstack = self.evaluate(array_ops.unstack(a, axis=j))

        self.assertAllEqual(expected, actual_unstack)

  def testAxis0Default(self):
    a = constant_op.constant([[1, 2, 3], [4, 5, 6]], name='a')
    unstacked = self.evaluate(array_ops.unstack(a))

    self.assertEqual(len(unstacked), 2)
    self.assertAllEqual(unstacked[0], [1, 2, 3])
    self.assertAllEqual(unstacked[1], [4, 5, 6])

  def testAxisOutOfRange(self):
    a = constant_op.constant([[1, 2, 3], [4, 5, 6]], name='a')
    with self.assertRaisesRegex(ValueError, r'axis = 2 not in \[-2, 2\)'):
      array_ops.unstack(a, axis=2)

  def testAxisOutOfNegativeRange(self):
    a = constant_op.constant([[1, 2, 3], [4, 5, 6]], name='a')
    with self.assertRaisesRegex(ValueError, r'axis = -3 not in \[-2, 2\)'):
      array_ops.unstack(a, axis=-3)

  def testZeroLengthDim(self):
    x = array_ops.zeros(shape=(0, 1, 2))
    y = self.evaluate(array_ops.unstack(x, axis=1)[0])
    self.assertEqual(y.shape, (0, 2))

  def testComplexGpu(self):
    if not test_util.is_gpu_available():
      self.skipTest('No GPU available')

    np.random.seed(7)
    with test_util.force_gpu():
      for shape in (2,), (3,), (2, 3), (3, 2), (4, 3, 2):
        for dtype in [np.complex64, np.complex128]:
          data = np.random.randn(*shape).astype(dtype)
          # Convert data to a single tensorflow tensor
          x = constant_op.constant(data)
          # Unstack into a list of tensors
          cs = array_ops.unstack(x, num=shape[0])
          self.assertEqual(type(cs), list)
          self.assertEqual(len(cs), shape[0])
          cs = [self.evaluate(c) for c in cs]
          self.assertAllEqual(cs, data)


if __name__ == '__main__':
  test.main()
