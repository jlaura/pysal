"""
PySAL ShapeFile Reader and Writer based on pure python shapefile module.

"""

__author__ = "Charles R Schmidt <schmidtc@gmail.com>"
__credits__ = "Copyright (c) 2009 Charles R. Schmidt"
__all__ = ['PurePyShpWrapper']

#import pysal
from pysal.core.FileIO2 import FileIOBase  # as FileIO
from pysal.core.util import shp_file
import pysal.cg as cg
from pysal.core.geodf.geoseries import GeoSeries

from warnings import warn
import unittest

STRING_TO_TYPE = {'POLYGON': cg.Polygon, 'POINT': cg.Point, 'POINTM':
                  cg.Point, 'POINTZ': cg.Point, 'ARC': cg.Chain, 'POLYGONZ': cg.Polygon}
TYPE_TO_STRING = {cg.Polygon: 'POLYGON', cg.Point: 'POINT', cg.Chain:
                  'ARC'}  # build the reverse map
#for key,value in STRING_TO_TYPE.iteritems():
#    TYPE_TO_STRING[value] = key


class PurePyShpWrapper(FileIOBase):
    """
    FileIO handler for ESRI ShapeFiles.

    Notes
    -----
    This class wraps _pyShpIO's shp_file class with the PySAL FileIO API.
    shp_file can be used without PySAL.

    Attributes
    ----------

    Formats     : list
                  A list of support file extensions
    Modes       : list
                  A list of support file modes

    Examples
    --------

    >>> import tempfile
    >>> f = tempfile.NamedTemporaryFile(suffix='.shp'); fname = f.name; f.close()
    >>> import pysal
    >>> i = pysal.open(pysal.examples.get_path('10740.shp'),'r')
    >>> o = pysal.open(fname,'w')
    >>> for shp in i:
    ...     o.write(shp)
    >>> o.close()
    >>> open(pysal.examples.get_path('10740.shp'),'rb').read() == open(fname,'rb').read()
    True
    >>> open(pysal.examples.get_path('10740.shx'),'rb').read() == open(fname[:-1]+'x','rb').read()
    True
    >>> import os
    >>> os.remove(fname); os.remove(fname.replace('.shp','.shx'))

    """
    FORMATS = ['shp', 'shx']
    MODES = ['w', 'r', 'wb', 'rb']

    def __init__(self, input_ds, mode='r'):
        super(PurePyShpWrapper, self).__init__(input_ds, mode=mode)
        self.pos = 0
        self.dataObj = None
        
        if self.mode == 'r' or self.mode == 'rb':
            self.__open()
        elif self.mode == 'w' or self.mode == 'wb':
            self.__create()
    
    @property
    def pos(self):
        return self._pos
    
    @pos.setter
    def pos(self, value):
        self._pos = value

    def __len__(self):
        if self.dataObj:
            return len(self.dataObj)
        else:
            return 0

    def __open(self):
        self.dataObj = shp_file(self.datapath)
        self.header = self.dataObj.header
        self.bbox = self.dataObj.bbox
        try:
            self.type = STRING_TO_TYPE[self.dataObj.type()]
        except KeyError:
            raise TypeError('%s does not support shapes of type: %s'
                            % (self.__class__.__name__, self.dataObj.type()))

    def __create(self):
        self.write = self.__firstWrite

    def __firstWrite(self, shape):
        self.type = TYPE_TO_STRING[type(shape)]
        if self.type == 'POINT':
            if len(shape) == 3:
                self.type = 'POINTM'
            if len(shape) == 4:
                self.type = 'POINTZ'
        self.dataObj = shp_file(self.datapath, 'w', self.type)
        self.write = self.__writer
        self.write(shape)

    def __writer(self, shape):
        if TYPE_TO_STRING[type(shape)] != self.type:
            raise TypeError("This file only supports %s type shapes" %
                            self.type)
        rec = {}
        rec['Shape Type'] = shp_file.SHAPE_TYPES[self.type]
        if self.type == 'POINT':
            rec['X'] = shape[0]
            rec['Y'] = shape[1]
            if len(shape) > 2:
                rec['M'] = shape[2]
            if len(shape) > 3:
                rec['Z'] = shape[3]
            shape = rec
        else:
            rec['BBOX Xmin'] = shape.bounding_box.left
            rec['BBOX Ymin'] = shape.bounding_box.lower
            rec['BBOX Xmax'] = shape.bounding_box.right
            rec['BBOX Ymax'] = shape.bounding_box.upper
            if self.type == 'POLYGON':
                holes = [hole[::-1] for hole in shape.holes if hole]
                    #holes should be in CCW order
                rec['NumParts'] = len(shape.parts) + len(holes)
                all_parts = shape.parts + holes
            else:
                rec['NumParts'] = len(shape.parts)
                all_parts = shape.parts
            partsIndex = [0]
            for l in map(len, all_parts)[:-1]:
                partsIndex.append(partsIndex[-1] + l)
            rec['Parts Index'] = partsIndex
            verts = sum(all_parts, [])
            verts = [(x, y) for x, y in verts]
            rec['NumPoints'] = len(verts)
            rec['Vertices'] = verts
        self.dataObj.add_shape(rec)
        self.pos += 1

    
    def _read(self):
        try:
            rec = self.dataObj.get_shape(self.pos)
        except IndexError:
            return None
        self.pos += 1
        if self.dataObj.type() == 'POINT':
            shp = self.type((rec['X'], rec['Y']))
        elif self.dataObj.type() == 'POINTZ':
            shp = self.type((rec['X'], rec['Y']))
            shp.Z = rec['Z']
            shp.M = rec['M']
        else:
            if rec['NumParts'] > 1:
                partsIndex = list(rec['Parts Index'])
                partsIndex.append(None)
                parts = [rec['Vertices'][partsIndex[i]:partsIndex[
                    i + 1]] for i in xrange(rec['NumParts'])]
                if self.dataObj.type() == 'POLYGON':
                    is_cw = map(pysal.cg.is_clockwise, parts)
                    vertices = [part for part, cw in zip(parts, is_cw) if cw]
                    holes = [part for part, cw in zip(parts, is_cw) if not cw]
                    if not holes:
                        holes = None
                    shp = self.type(vertices, holes)
                else:
                    vertices = parts
                    shp = self.type(vertices)
            elif rec['NumParts'] == 1:
                vertices = rec['Vertices']
                if self.dataObj.type() == 'POLYGON' and not cg.is_clockwise(vertices):
                    ### SHAPEFILE WARNING: Polygon %d topology has been fixed. (ccw -> cw)
                    warn("SHAPEFILE WARNING: Polygon %d topology has been fixed. (ccw -> cw)" % (self.pos), RuntimeWarning)
                    print "SHAPEFILE WARNING: Polygon %d topology has been fixed. (ccw -> cw)" % (self.pos)

                shp = self.type(vertices)
            else:
                warn("Polygon %d has zero parts" % self.pos, RuntimeWarning)
                shp = self.type([[]])
                #raise ValueError, "Polygon %d has zero parts"%self.pos
        #I think we can drop this ID nonsense moving to a dataframe
        #if self.ids:
        #    shp.id = self.rIds[self.pos - 1]  # shp IDs start at 1.
        #else:
        #    shp.id = self.pos  # shp IDs start at 1.
        return shp

    def read(self, n=-1):
        """
        If n < 0 read all entires
        If n = 0 read none
        If n > 0 read n entries
        """
        #TODO: I do not want a result as a list, I want a dataframe.
        result = []
        if n < 0:
            #Treating as an iterator was slick, but why?
            while 1:
                res = self._read()
                if res:
                    result.append(res)
                else:
                    break
            self.pos = 0  #Must reset pos
            geoms = [i.__geo_interface__ for i in result]
            return GeoSeries(geoms)
        
        elif n == 0:
            return None
        else:
            result = []
            for i in range(0,n):
                try:
                    result.append(self._read())
                except StopIteration:
                    break
            geoms = [i.__geo_interface__ for i in result]
            return GeoSeries(geoms)
    
    def close(self):
        self.dataObj.close()
        pysal.core.FileIO.FileIO.close(self)

