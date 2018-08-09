#!/usr/bin/python
# coding=utf-8

"""
.. module:: phobos.utils.general
    :platform: Unix, Windows, Mac
    :synopsis: This module contains general functions to use in operators and custom scripts

.. moduleauthor:: Kai von Szadowski

Copyright 2017, University of Bremen & DFKI GmbH Robotics Innovation Center

This file is part of Phobos, a Blender Add-On to edit robot models.

Phobos is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License
as published by the Free Software Foundation, either version 3
of the License, or (at your option) any later version.

Phobos is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with Phobos.  If not, see <http://www.gnu.org/licenses/>.
"""

import bpy
import mathutils
import math
from phobos.phoboslog import log
from . import selection as sUtils
from . import naming as nUtils
from . import blender as bUtils
from . import io as ioUtils
from .. import defs


def addDictionaryToObj(dict, obj, category=None):
    # DOCU add some docstring
    for key, value in dict:
        obj[(category+'/'+key) if category else key] = value


def getCombinedTransform(obj, effectiveparent):
    """Get the combined transform of the object relative to the effective parent.

    This combines all transformations in the parenting hierarchy up to the specified effective
    parent.

    Args:
        obj (bpy.types.Object): the child object
        effectiveparent (bpy.types.Object): the effective parent of the child object

    Returns:
        bpy.types.Matrix -- the combined transformations of the child object
    """
    parent = obj.parent
    matrix = obj.matrix_local
    while parent != effectiveparent and parent is not None:
        matrix = parent.matrix_local * matrix
        parent = parent.parent
    return matrix


def restructureKinematicTree(link, root=None):
    """Restructures a tree such that the *link* provided becomes the root of the tree. For
    instance, the following tree:
             A
           /  \
          B    C
         / \    \
        D   E    F
    would, using the call restructureKinematicsTree(C), become:
            C
          /  \
         A    F
        /
       B
      / \
     D   E
     Currently, this function ignores all options such as unselected or hidden objects.

    Args:
      link: the link which will become the new root object
      root: the current root object
    (otherwise, phobos.utils.selection.getRoot will be used) (Default value = None)

    Returns:

    """
    if not root:
        root = sUtils.getRoot(link)
    links = [link]
    obj = link

    # stop right now when the link is already root
    if not obj.parent:
        log('No restructure necessary. Link is already root.', 'INFO')
        return

    # gather chain of links ascending the tree
    while obj.parent.name != root.name:
        obj = obj.parent
        if obj.phobostype == 'link':
            links.append(obj)
    links.append(root)

    log("Unparenting objects for restructure: " + str([link.name for link in links]) + ".", 'DEBUG')
    # unparent all links
    sUtils.selectObjects(links, True)
    bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')

    log("Restructuring objects for new hierarchy.", 'DEBUG')
    for i in range(len(links) - 1):
        parent = links[i]
        child = links[i + 1]
        sUtils.selectObjects((parent, child), True, active=0)
        bpy.ops.object.parent_set(type='BONE_RELATIVE')

    log("Copying model information from old root.", 'DEBUG')
    # copy properties
    if 'modelname' in root:
        link['modelname'] = root['modelname']
        del root['modelname']
    if 'version' in root:
        link['version'] = root['version']
        del root['version']
    log("Restructured kinematic tree to new root: {}.".format(link.name), 'INFO')


def getNearestCommonParent(objs):
    """Returns hierarchically lowest common parent of the provided objects

    Args:
        objs: list of objects (bpy_types.Object)
    """
    anchor = objs[0]  # pick one link as the anchor link
    rest = objs[1:]  # get other links to iterate over
    in_all = False  # this will be true if all 'rest' branches have parent as a common parent
    parent = anchor  # the candidate for common parent
    inter_objects = set()
    while not in_all and parent.parent:
        in_all = True
        parent = parent.parent  # go up the anchor branch
        inter_objects.add(parent)
        for obj in rest:  # start at base of each rest branch
            o = obj
            while o.parent and o.parent != parent:  # as long as there is a parent that is not the candidate parent
                o = o.parent
                inter_objects.add(o)
            if o.parent != parent:  # check which break condition happened, break if not arrived at parent
                in_all = False
                break
    if not in_all:  # this is only true if none of the branches set it to False and broke afterwards
        return None
    else:
        inter_objects.remove(parent)
        return parent, list(inter_objects)


def instantiateSubmodel(submodelname, instancename, size=1.0):
    """Creates an instance of the submodel specified by the submodelname.

    The instance receives the definitions of the group as it is generated.

    Args:
      submodelname: name of the submodel (Blender group) to create an
    instance of
      instancename: name the instance object will receive
      size:  (Default value = 1.0)

    Returns:

    """
    submodel = None
    interfaces = None

    # find the existing group for submodel and interface
    for group in bpy.data.groups:
        # search for namespaced groups with the exact name
        if ':' in group.name and submodelname == group.name:
            submodel = group
        if (group.name.startswith('interfaces:') and
                submodelname.split(':')[1] in group.name):
            interfaces = group

    if not submodel:
        log('Selected submodel is not defined.', 'ERROR')
    if not interfaces:
        log('No interfaces defined for this submodel.', 'INFO')

    # add the submodel and write in data
    bpy.ops.object.group_instance_add(group=submodel.name)
    submodelobj = bpy.context.active_object
    submodelobj.phobostype = 'submodel'
    submodelobj['submodeltype'] = submodel.name.split(':')[0]
    # TODO currently this works only by name binding, we should add links to
    # the group here
    submodelobj['submodelname'] = submodelname
    # copy custom props from group to instance
    for key in submodel.keys():
        submodelobj[key] = submodel[key]
    submodelobj.name = instancename
    submodelobj.empty_draw_size = size

    # add the interfaces if available
    if interfaces:
        # create group and make real
        bpy.ops.object.group_instance_add(group=interfaces.name)
        bpy.ops.object.duplicates_make_real()

        # write interface parameters and change namespace
        for obj in bpy.context.selected_objects:
            nUtils.addNamespace(obj, instancename)
            obj.name = obj.name.rsplit('.')[0]
            obj['submodeltype'] = 'interface'
            bUtils.toggleTransformLock(obj, True)

        # parent interfaces to submodel empty
        sUtils.selectObjects(
            objects=[submodelobj] + bpy.context.selected_objects,
            clear=True, active=0)
        bpy.ops.object.parent_set(type='OBJECT')

        # delete empty parent object of interfaces
        sUtils.selectObjects(objects=[a for a in bpy.context.selected_objects
                                      if a.type == 'EMPTY' and
                                      'submodeltype' in a and
                                      a['submodeltype'] == 'interface'],
                             clear=True, active=0)
        bpy.ops.object.delete(use_global=False)
    return submodelobj


def defineSubmodel(submodelname, submodeltype, version='', objects=None):
    """Defines a new submodule group with the specified name and type.

    The group will be named like so:
        'submodeltype:submodelname/version'

    Objects with the phobostype 'interface' (if present) are handled separately
    and put into a respective submodel group (which features the 'interface'
    submodeltype).

    If the version is omitted, the respective part of the name is dropped, too.
    If no object list is provided the objects are derived from selection.
    The submodeltype is also added as dict entry to the group in Blender.

    The selected objects are moved to the respective layer for submodels or
    interfaces.

    Args:
      submodelname: descriptive name of the submodel
      submodeltype: type of the submodel (e.g. 'fmu', 'mechanics')
      version: a version string (e.g. '1.0', 'dangerous') (Default value = '')
      objects: the objects which belong to the submodel (None will derive
    objects from the selection) (Default value = None)

    Returns:
      a tuple of the submodelgroup and interfacegroup/None

    """
    if not objects:
        objects = bpy.context.selected_objects

    # split interface from physical objects
    interfaces = [i for i in objects if i.phobostype == 'interface']
    physical_objects = [p for p in objects if p.phobostype != 'interface']

    # make the physical group
    sUtils.selectObjects(physical_objects, True, 0)
    submodelgroupname = submodeltype + ':' + submodelname
    if version != '':
        submodelgroupname += '/' + version
    if submodelgroupname in bpy.data.groups.keys():
        log('submodelgroupname ' + 'already exists', 'WARNING')
    bpy.ops.group.create(name=submodelgroupname)
    submodelgroup = bpy.data.groups[submodelgroupname]
    submodelgroup['submodeltype'] = submodeltype
    submodelgroup['version'] = version

    modeldefs = defs.definitions['submodeltypes'][submodeltype]

    # copy the definition parameters to the group properties
    for key in modeldefs['definitions']:
        submodelgroup[key] = modeldefs['definitions'][key]

    # move objects to submodel layer
    for obj in physical_objects:
        obj.layers = bUtils.defLayers(defs.layerTypes['submodel'])
    log('Created submodel group ' + submodelname + ' of type "' + submodeltype
        + '".', 'DEBUG')

    interfacegroup = None
    # make the interface group
    if interfaces:
        sUtils.selectObjects(interfaces, True, 0)
        interfacegroupname = 'interfaces:' + submodelname
        if version != '':
            interfacegroupname += '/' + version
        # TODO what about overwriting groups with same names?
        bpy.ops.group.create(name=interfacegroupname)
        interfacegroup = bpy.data.groups[interfacegroupname]
        interfacegroup['submodeltype'] = 'interfaces'

        # copy interface definitions from submodel definitions
        for key in modeldefs['interfaces']:
            interfacegroup[key] = modeldefs['interfaces'][key]

        # move objects to interface layer
        for obj in interfaces:
            obj.layers = bUtils.defLayers(defs.layerTypes['interface'])
        log('Created interface group for submodel ' + submodelname + '.',
            'DEBUG')
    else:
        log('No interfaces for this submodel.', 'DEBUG')

    for i in interfaces:
        i.show_name = True
    return (submodelgroup, interfacegroup)


def removeSubmodel(submodelname, submodeltype, version='', interfaces=True):
    """Removes a submodel definition from the Blender project.
    Returns True or False depending on whether groups have been removed or not.

    Args:
      submodelname: the name of the submodel
      submodeltype: the submodeltype of the submodel
      version: optional version of the submodel (Default value = '')
      interfaces: True if interface should also be deleted, else False. (Default value = True)

    Returns:
      True if groups have been removed, else False.

    """
    # build the group name to look for
    submodelgroupname = submodeltype + ':' + submodelname
    if version != '':
        submodelgroupname += '/' + version

    # remove the submodelgroup
    if submodelgroupname in bpy.data.groups:
        bpy.data.groups.remove(bpy.data.groups[submodelgroupname])
        if not interfaces:
            return True

    if interfaces:
        interfacegroupname = 'interfaces:' + submodelname
        if version != '':
            interfacegroupname += '/' + version

        if interfacegroupname in bpy.data.groups:
            bpy.data.groups.remove(bpy.data.groups[interfacegroupname])
            return True
    return False


def createInterface(ifdict, parent=None):
    """Create an interface object and optionally parent to existing object.

    ifdict is expected as:
    ifdict = {'type': str,
              'direction': str,
              'model': str,
              'name': str,
              'parent': bpy.types.Object (optional),
              'scale': float (optional)
              }

    Args:
        ifdict(dict): interface data
        parent(bpy.types.Object): designated parent object

    Returns(bpy.data.Object): newly created interface object

    """
    if not parent:
        try:
            parent = ifdict['parent']
            assert isinstance(parent, bpy.types.Object)
        except (AttributeError, AssertionError, KeyError):
            parent = None
    location = parent.matrix_world.translation if parent else mathutils.Vector()
    rotation = parent.matrix_world.to_euler() if parent else mathutils.Euler()

    model = ifdict['model'] if 'model' in ifdict else 'default'
    templateobj = ioUtils.getResource(('interface', model, ifdict['direction']))
    scale = ifdict['scale'] if 'scale' in ifdict else 1.0
    ifobj = bUtils.createPrimitive(ifdict['name'], 'box', (1.0, 1.0, 1.0), defs.layerTypes['interface'],
                                   plocation=location, protation=rotation, phobostype='interface')
    nUtils.safelyName(ifobj, ifdict['name'], 'interface')
    ifobj.data = templateobj.data
    ifobj.scale = (scale,)*3
    ifobj['interface/type'] = ifdict['type']
    ifobj['interface/direction'] = ifdict['direction']
    bpy.ops.object.make_single_user(object=True, obdata=True)


def toggleInterfaces(interfaces=None, modename='toggle'):
    modedict = {'toggle': 0, 'activate': 1, 'deactivate': 2}
    mode = modedict[modename]
    if not interfaces:
        interfaces = [i for i in bpy.context.selected_objects if i.phobostype == 'interface']
    for i in interfaces:
        if mode == 0:
            i.show_name = not i.show_name
        elif mode == 1:
            i.show_name = True
        elif mode == 2:
            i.show_name = False


def connectInterfaces(parentinterface, childinterface, transform=None):
    # first check if the interface is child of the root object and if not, restructure the tree
    root = sUtils.getRoot(childinterface)
    parent = childinterface.parent
    if root != parent:
        restructureKinematicTree(parent)
    childsubmodel = childinterface.parent

    # connect the interfaces
    sUtils.selectObjects(objects=[parentinterface], clear=True, active=0)
    bpy.ops.object.make_single_user(object=True, obdata=True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    sUtils.selectObjects(objects=[childinterface], clear=True, active=0)
    bpy.ops.object.make_single_user(object=True, obdata=True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
    sUtils.selectObjects(objects=[childinterface, childsubmodel], clear=True, active=0)
    bpy.ops.object.parent_set(type='OBJECT')
    sUtils.selectObjects(objects=[parentinterface, childinterface], clear=True, active=0)
    bpy.ops.object.parent_set(type='OBJECT')

    loc, rot, sca = parentinterface.matrix_world.decompose()
    # apply additional transform (ignoring the scale of the parent interface)
    if not transform:
        transform = mathutils.Euler((math.radians(180.0), 0.0, math.radians(180.0)), 'XYZ').to_matrix().to_4x4()

    childinterface.matrix_world = mathutils.Matrix.Translation(loc) * rot.to_matrix().to_4x4() * transform

    # TODO clean this up
    # try:
    #    del childsubmodel['modelname']
    # except KeyError:
    #    pass
    #TODO: re-implement this for MECHANICS models
    # try:
    #     # parent visual and collision objects to new parent
    #     children = sUtils.getImmediateChildren(parent, ['visual', 'collision', 'interface'])
    #     print(children)
    #     sUtils.selectObjects(children, True, 0)
    #     bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
    #     print()
    #     sUtils.selectObjects([sUtils.getEffectiveParent(parent, ignore_selection=True)] + children, True, 0)
    #     bpy.ops.object.parent_set(type='BONE_RELATIVE')
    # except (IndexError, AttributeError):
    #     pass  # no objects to re-parent
    parentinterface.show_name = False
    childinterface.show_name = False


def disconnectInterfaces(parentinterface, childinterface, transform=None):
    # unparent the child
    sUtils.selectObjects(objects=[childinterface], clear=True, active=0)
    bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')

    # select the former parent of the interface as new root
    if childinterface.children and len(childinterface.children) > 0:
        # prefer submodel instances
        for child in childinterface.children:
            if child.phobostype == 'submodel':
                root = child
                break
        # otherwise just use the first child
        else:
            root = childinterface.children[0]

    # restructure the kinematic tree to make the interface child of the submodel again
    sUtils.selectObjects(objects=[root], clear=True, active=0)
    bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
    sUtils.selectObjects(objects=[root, childinterface], clear=True, active=0)
    bpy.ops.object.parent_set(type='OBJECT')

    # apply additional transform
    if transform:
        childinterface.matrix_world = root.matrix_world * transform

    # make the interfaces active again
    parentinterface.show_name = True
    childinterface.show_name = True


def getPropertiesSubset(obj, category=None):
    if not category:
        category = obj.phobostype
    try:
        dict = {key.replace(category+'/', ''): value
                for key, value in obj.items() if key.startswith(category+'/')}
    except KeyError:
        log("Failed filtering properties for category " + category, "ERROR")
    return dict


def mergeLinks(links, targetlink, movetotarget=False):
    for link in links:
        if movetotarget:
            link.matrix_world = targetlink.matrix_world
        sUtils.selectObjects([link], clear=True, active=0)
        bpy.ops.object.select_grouped(type='CHILDREN')
        bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
        sUtils.selectObjects([targetlink] + bpy.context.selected_objects, clear=True, active=0)
        try:
            bpy.ops.object.parent_set(type='BONE_RELATIVE')
        except RuntimeError as e:
            log("Cannot resolve new parent hierarchy: " + str(e), 'ERROR')
        del link


def addAnnotationObject(obj, annotation, name=None, size=0.1, namespace=None):
    """Add a new annotation object with the specified annotations to the object.

    The annotation object will receive 'annotation_object' as its default name, unless a name is
    provided. Naming is done using :function:`phobos.utils.naming.safelyName`.

    The annotation object will be scaled according to the `size` parameter.

    If `namespace` is provided, the annotations will be saved with this string prepended.
    This is done using :function:`addAnnotation`.

    Args:
        obj (bpy.types.Object): object to add annotation object to
        annotation (dict): annotations that will be added
        name (str, optional): name for the new annotation object
        size (int/float, optional): size of the new annotation object
        namespace (str, optional): namespace that will be prepended to the annotations

    Returns:
        bpy.types.Object - the new annotation object
    """
    loc = obj.matrix_world.to_translation()
    bpy.ops.object.empty_add(type='SPHERE', location=loc,
                             layers=bUtils.defLayers(defs.layerTypes['annotation']))
    annot_obj = bpy.context.scene.objects.active
    annot_obj.phobostype = 'annotation'
    annot_obj.empty_draw_size = size

    # make sure all layers are enabled for parenting
    originallayers = list(bpy.context.scene.layers)
    bpy.context.scene.layers = [True for i in range(20)]

    # parent annotation object
    sUtils.selectObjects([obj, annot_obj], clear=True, active=0)
    bpy.ops.object.parent_set(type='OBJECT')

    bpy.context.scene.layers = originallayers
    if not name:
        nUtils.safelyName(annot_obj, 'annotation_object')
    else:
        nUtils.safelyName(annot_obj, name)

    addAnnotation(annot_obj, annotation, namespace=namespace)
    return annot_obj


def addAnnotation(obj, annotation, namespace=None):
    """Adds the specified annotations to the object.

    If provided, the namespace will be prepended to the annotation keys and separated with a /.

    Args:
        obj (bpy.types.Object): object to add the annotations to
        annotation (dict): annotations to add to the object
        namespace (str, optional): namespace which will be prepended to the annotations
    """
    for key, value in annotation.items():
        obj[str(namespace + '/' if namespace else '') + key] = value


def removeProperties(obj, props, recursive=False):
    """Removes a list of custom properties from the specified object.

    The specified property list can contain names with wildcards at the end (e.g. sensor*).

    If recursive is set, the properties will be removed recursively from all children, too.

    Args:
        obj (bpy.types.Object): object to remove the properties from
        props (list(str)): list of property names, which will be removed from the object
        recursive (bool): if True, the properties will be removed recursively from the children, too
    """
    for prop in props:
        if prop in obj:
            del obj[prop]
        elif prop[-1] == '*':
            for objprop in obj.keys():
                if objprop.startswith(prop[:-1]):
                    del obj[objprop]

    if recursive:
        for child in obj.children:
            removeProperties(child, props, recursive=recursive)
