import unittest

from util import join_with_colon


class Util(unittest.TestCase):
    def test_join_with_colon_empty(self):
        actual = join_with_colon()
        self.assertEqual('', actual)

    def test_join_with_colon_concat(self):
        actual = join_with_colon('a', 'b')
        self.assertEqual('a : b', actual)
