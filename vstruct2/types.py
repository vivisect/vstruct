import io
import codecs

from . import bases as vs_bases

# NOTE: keep this namespace super clean so it's safe to
#       use this via "from vstruct2.types import *"

'''
VStruct types module contains a standard set of working field types
for use in building VStruct definitions.
'''

class VStruct(vs_bases.v_base,object):
    '''
    Base class for all structure definitions.

    The VStruct class facilitates structure definition, parsing, and emiting
    by allowing users to define fields with specific types.  Once defined, VStruct
    based structure classes are capable of automagically parsing data structure
    hierarchies as well as emiting bytes.

    Example:

        class woot(VStruct):

            def __init__(self):
                self.x = int8()
                self.y = uint32()
                self.z = vbytes(6)

        w = woot()
        w.vsParse( bytebuffer )

        # we may now access the structure fields directly from our
        # object which will return proper pythonic types for the
        # field accesses:

        print('x: %d y: %d' % (w.x, w.y))

        # additionally, we may set pre-defined fields using python types
        w.y = 90

        # and re-serialize the newly modified structure back to bytes
        w.vsEmit()
    '''

    def __init__(self, align=0):
        vs_bases.v_base.__init__(self)
        self._vs_endian = None
        self._vs_isprim = False

        self._vs_fields = {}
        self._vs_fieldorder = []

        # from a tiny bit of evil from vstruct1
        self._vs_name = self.__class__.__name__

    def vsGetTypeName(self):
        return self._vs_name

    def __iter__(self):
        for name in self._vs_fieldorder:
            yield ( name, self._vs_fields.get(name) )

    def vsEmit(self):
        '''
        Return bytes for the current values in the structure definition.
        '''
        fd = io.BytesIO()
        for off,prim in self.vsPrims():
            fd.seek(off)
            fd.write( prim.vsEmit() )
        fd.seek(0)
        return fd.read()

    def vsParse(self, buf, offset=0, writeback=False):
        '''
        Parse the given python bytes into structure values.
        '''
        retoff = offset
        for off,prim in self.vsPrims():
            retoff = prim.vsParse(buf, offset=offset+off, writeback=writeback)
        self._fire_onset()
        return retoff

    def vsLoad(self, fd, offset=0, writeback=False):
        retoff = offset
        for off,prim in self.vsPrims():
            retoff = prim.vsLoad(fd, offset=offset+off, writeback=writeback)
        self._fire_onset()
        return retoff

    def vsPrint(self, indent=0, addr=0):
        off = 0
        pad = ' ' * indent

        print('%.8x: %s%s' % (addr,pad,self.__class__.__name__))
        for name,field in self:
            typename = field.__class__.__name__
            print( '%.8x: %s%s %s = %s (%s)' % (addr+off,pad,typename,name,field._prim_getval(),repr(field)) )
            if not field._vs_isprim:
                field.vsPrint(indent=indent+2,addr=addr+off)

            off += len(field)

    def _vs_prims(self):
        # recursive primitive *yielder* ( allows resizing while yielding )
        for name in self._vs_fieldorder:
            field = self._vs_fields.get(name)
            # for non-primitives, "recurse"
            if not field._vs_isprim:
                for f in field._vs_prims():
                    yield f

                continue

            yield field

    def vsPrims(self):
        '''
        Yield (offset,field) tuples for each contained primitive

        NOTE: this is implemented as a yield generator to allow resizing
        '''
        offset = 0
        for prim in self._vs_prims():
            # FIXME do alignment here
            yield (offset,prim)
            offset += prim.vsSize()

    def vsSize(self):
        '''
        Returns the current size of the structure in bytes.
        '''
        prims = list( self.vsPrims() )
        if not prims:
            return 0
        off,field = prims[-1]
        return off + field.vsSize()

    def vsGetField(self, name):
        x = self._vs_fields.get(name)
        if x == None:
            raise Exception("Invalid field: %s" % name)
        return x

    def vsHasField(self, name):
        '''
        Test whether this structure contains a field with the
        given name....
        Example:
        if x.vsHasField('woot'):
            print 'STRUCT HAS WOOT FIELD!'
        '''
        return self._vs_fields.get(name) != None

    def _prim_getval(self):
        return self

    def __getattr__(self, name):
        ret = self._vs_fields.get(name)
        if ret != None:
            return ret._prim_getval()
        raise AttributeError('%s has no field %s' % (self.__class__.__name__,name))

    def __setattr__(self, name, valu):
        if name.startswith('_vs_'):
            return super(VStruct,self).__setattr__(name,valu)

        # check for endian-ness override
        if self._vs_endian and isinstance(valu,vs_bases.v_int):
            valu._vs_endian = self._vs_endian

        if isinstance(valu,vs_bases.v_base):
            field = self._vs_fields.get(name)
            if field == None:
                self._vs_fieldorder.append(name)
            self._vs_fields[name] = valu
            return

        field = self._vs_fields.get(name)
        if field != None:
            field._prim_setval( valu )
            return

        return super(VStruct,self).__setattr__(name,valu)

    def __getitem__(self, name):
        return self._vs_fields.get(name)

    def __setitem__(self, name, valu):
        field = self._vs_fields.get(name)

        if isinstance(valu,vs_bases.v_base):
            self._vs_fields[name] = valu
            if field == None:
                self._vs_fieldorder.append( name )

            return

        if field == None:
            raise Exception('Undefined Field: %s' % name)

        field._prim_setval( valu )

class VArray(VStruct):

    def __init__(self, fields=()):
        VStruct.__init__(self)

        for i,f in enumerate(fields):
            self[i] = f

    def vsAddElement(self, elem):
        """
        Used to add elements to an array
        """
        new_idx = len(self._vs_fields)
        self[new_idx] = elem

    def vsAddElements(self, count, eclass):
        for i in xrange(count):
            self.vsAddElement(eclass())

class vbytes(vs_bases.v_prim):
    '''
    Fixed width binary bytes field.
    '''
    def __init__(self, size=0,val=b''):
        vs_bases.v_prim.__init__(self, size=size,valu=val)
        self._vs_value  = val
        self._vs_length = size

    def _prim_emit(self, x):
        return x.ljust(self.vsSize(), b'\x00')

    def _prim_norm(self, x):
        return bytes(x)

    def _prim_parse(self, byts, offset):
        return bytes( byts[offset:offset + self.vsSize() ] )

    ## FIXME - may need to add function to update length whenever valu is changed?

class cstr(vs_bases.v_prim):
    '''
    Fixed width string type.

    Assignments will be NULL padded to match size.

    Example:

        class woot(VStruct):
            def __init__(self):
                self.x = cstr(8)

        w = woot()
        w.x = 'hi'

        w.vsEmit() # emit's 8 bytes

    '''
    def __init__(self, size=0, valu='', encoding='utf8'):
        self._vs_encoding = encoding
        vs_bases.v_prim.__init__(self,size=size,valu=valu)

    def _prim_emit(self, x):
        return x.encode( self._vs_encoding ).ljust( self.vsSize(), b'\x00' )

    def _prim_norm(self, x):
        buf = x.encode( self._vs_encoding )
        return buf[:self.vsSize()].decode( self._vs_encoding )

    def _prim_parse(self, byts, offset):
        buf = byts[offset:offset + self.vsSize()]
        return buf.decode( self._vs_encoding ).split('\x00')[0]

class zstr(vs_bases.v_prim):
    r'''
    A dynamically sized ( NULL terminated ) string type.

    Parsing bytes will dynamically resize the object to the first NULL.

    Example:
        class woot(VStruct):
            def __init__(self):
                self.x = zstr()
                self.y = uint16()

        w = woot()
        w.vsParse(b'this is some text\x00\x03\x00')

        print(w.y) # prints 3

        # assignment auto NULL pads
        w = woot()
        w.x = 'hi there'
        w.y = 0x4141

        w.vsEmit() # emits b'hi there\x00AA'
    '''
    def __init__(self, size=0, valu='', encoding='utf8'):
        self._vs_encoding = encoding
        vs_bases.v_prim.__init__(self, size=size, valu=valu)

    def vsSize(self):
        self._prim_getval()
        return self._vs_size

    def _prim_norm(self, x):
        buf = (x + '\x00').encode( self._vs_encoding )
        self.vsResize( len(buf) )
        return x

    def _prim_emit(self, x):
        return (x + '\x00').encode( self._vs_encoding )

    def _prim_parse(self, buf, off):
        info = {}
        gen = self._prim_yield_bytes(buf, off, info)
        return self._prim_fromgen(gen,info)

    def _prim_load(self, fd, off):
        info = {}
        gen = self._prim_yield_fd(fd,off,info)
        return self._prim_fromgen(gen,info)

    def _prim_fromgen(self, yielder, info):
        chars = []
        # not exactly a model of efficiency...
        for c in codecs.iterdecode(yielder, self._vs_encoding):
            if ord(c) == 0:
                break
            chars.append(c)

        self.vsResize(info['size'])
        return ''.join(chars)

    def _prim_yield_bytes(self, buf, off, info):
        info['size'] = 0
        for i in range(len(buf) - off):
            offi = off + i
            b = buf[offi:offi+1]
            info['size'] += 1
            yield b

    def _prim_yield_fd(self, fd, off,info):
        fd.seek(off)
        info['size'] = 0
        while True:
            b = fd.read(1)
            if not b:
                break

            info['size'] += 1
            yield b

class int8(vs_bases.v_int):
    '''
    Signed 8 bit integer type
    '''
    def __init__(self, valu=0, endian='little'):
        vs_bases.v_int.__init__(self, valu=valu, size=1, endian=endian, signed=True)

class int16(vs_bases.v_int):
    '''
    Signed 16 bit integer type
    '''
    def __init__(self, valu=0, endian='little'):
        vs_bases.v_int.__init__(self, valu=valu, size=2, endian=endian, signed=True)

class int32(vs_bases.v_int):
    '''
    Signed 32 bit integer type
    '''
    def __init__(self, valu=0, endian='little'):
        vs_bases.v_int.__init__(self, valu=valu, size=4, endian=endian, signed=True)

class int64(vs_bases.v_int):
    '''
    Signed 64 bit integer type
    '''
    def __init__(self, valu=0, endian='little'):
        vs_bases.v_int.__init__(self, valu=valu, size=8, endian=endian, signed=True)

class uint8(vs_bases.v_int):
    '''
    Unsigned 8 bit integer type
    '''
    def __init__(self, valu=0, endian='little', enum=None):
        vs_bases.v_int.__init__(self, valu=valu, size=1, endian=endian, enum=enum)

class uint16(vs_bases.v_int):
    '''
    Unsigned 16 bit integer type
    '''
    def __init__(self, valu=0, endian='little', enum=None):
        vs_bases.v_int.__init__(self, valu=valu, size=2, endian=endian, enum=enum)

class uint32(vs_bases.v_int):
    '''
    Unsigned 32 bit integer type
    '''
    def __init__(self, valu=0, endian='little', enum=None):
        vs_bases.v_int.__init__(self, valu=valu, size=4, endian=endian, enum=enum)

class uint64(vs_bases.v_int):
    '''
    Unsigned 64 bit integer type
    '''
    def __init__(self, valu=0, endian='little', enum=None):
        vs_bases.v_int.__init__(self, valu=valu, size=8, endian=endian, enum=enum)

class ptr32(vs_bases.v_int):
    def __init__(self, valu=0, endian='little'):
        vs_bases.v_int.__init__(self, valu=valu, size=4, endian=endian)

class ptr64(vs_bases.v_int):
    def __init__(self, valu=0, endian='little'):
        vs_bases.v_int.__init__(self, valu=valu, size=8, endian=endian)

def varray(size, cls, *args, **kwargs):
    '''
    Dynamically generate an VArray sublcass with "size" fields of type "cls"

    Example:

        cls = varray(10,uint32)

    # FIXME __mul__ for classes?

    '''

    def clsinit(self):
        fields = [ cls(*args,**kwargs) for i in range(size) ]
        VArray.__init__(self,fields)

    name = '%s_Array_%d' % (cls.__name__,size)
    return type(name,(VArray,),{'__init__':clsinit})

class venum(object):
    '''
    A venum class is used to define a set of enumeration values.

    Example:

        foo = venum()
        foo.TYPE_1  = 1
        foo.TYPE_2  = 2

        class woot(VStruct):
            def __init__(self):
                self.y = uint16(enum=foo)

        # foo[2] -> 'TYPE_2'
        # foo['TYPE_2'] -> 2

    Notes:

        * provide as enum param to int ctors for auto-repr

    '''
    def __init__(self):
        object.__setattr__(self, '_vs_enum_map', {})

    def __setattr__(self, name, valu):
        self._vs_enum_map[valu] = name
        self._vs_enum_map[name] = valu
        return object.__setattr__(self, name, valu)

    def __getitem__(self, item):
        return self._vs_enum_map.get(item)
