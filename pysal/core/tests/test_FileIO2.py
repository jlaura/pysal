import unittest

import pysal

class TestShp(unittest.TestCase):
    """
    Normally, I would use a realtive import and test
    the module directly, but I also want to test
    monkey patching in FileIO2 to pysal.open...

    What do you think is the best form?
    """

    def setUp(self):
        self.ds = pysal.open(pysal.examples.get_path('columbus.shp'), 'r')

    def test_shapefile_length(self):
        self.assertEqual(len(self.ds), 49)

    def test_full_shapefile_read(self):
        geoms = self.ds.read()
        self.assertEqual(len(geoms[5]), 7)

    def test_partial_shapefile_read(self):
        geoms = self.ds.read(6)
