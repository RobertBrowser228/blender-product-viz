import bpy, math
from mathutils import Vector

CURVE_NAME  = "cont-up.001"
SPLIT_NAME  = "cont-down.001"     # служебный вектор = граница зон
PRIM_NAME   = "chain-55"
FANCY_NAME  = "chain-55"

SPACING_MM   = 7.0    # шаг вдоль кривой
PRIM_ROW_MM  = 15.0    # шаг вниз в синей зоне
FANCY_ROW_MM = 15.0    # шаг вниз в красной зоне
TOTAL_MM     = 500.0   # полная глубина
TWIST_DEG    = 8.0     # доворот на ряд

NG_NAME, MOD_NAME = "NG_ChainLOD", "DI_ChainLOD"

curve = bpy.data.objects.get(CURVE_NAME)
split = bpy.data.objects.get(SPLIT_NAME)
prim  = bpy.data.objects.get(PRIM_NAME)
fancy = bpy.data.objects.get(FANCY_NAME)
assert curve and split and prim and fancy, "не найдены исходные объекты"

usc = bpy.context.scene.unit_settings.scale_length or 1.0
def mm(v): return (v / 1000.0) / usc

def top_z(ob):
return max((ob.matrix_world @ Vector(c)).z for c in ob.bound_box)

# граница зон: верх служебного вектора относительно верха кривой

zone_mm = (top_z(curve) - top_z(split)) * usc * 1000.0
zone_mm = max(0.0, min(zone_mm, TOTAL_MM))

prim_rows  = int(zone_mm // PRIM_ROW_MM)
fancy_rows = int((TOTAL_MM - prim_rows * PRIM_ROW_MM) // FANCY_ROW_MM)

old = bpy.data.node_groups.get(NG_NAME)
if old:
bpy.data.node_groups.remove(old)
ng = bpy.data.node_groups.new(NG_NAME, "GeometryNodeTree")
i = ng.interface
i.new_socket("Geometry", in_out='INPUT',  socket_type='NodeSocketGeometry')
i.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')

n, L = ng.nodes, ng.links.new
gin  = n.new("NodeGroupInput");  gin.location  = (-1200, 0)
gout = n.new("NodeGroupOutput"); gout.location = ( 1000, 0)

c2p = n.new("GeometryNodeCurveToPoints"); c2p.location = (-1020, 0)
c2p.mode = 'LENGTH'
c2p.inputs["Length"].default_value = mm(SPACING_MM)

sna = n.new("GeometryNodeStoreNamedAttribute"); sna.location = (-840, 0)
sna.data_type, sna.domain = 'FLOAT_VECTOR', 'POINT'
sna.inputs["Name"].default_value = "di_tang"
L(gin.outputs[0], c2p.inputs["Curve"])
L(c2p.outputs["Points"],  sna.inputs["Geometry"])
L(c2p.outputs["Tangent"], sna.inputs["Value"])

tang = n.new("GeometryNodeInputNamedAttribute"); tang.location = (-840, 560)
tang.data_type = 'FLOAT_VECTOR'
tang.inputs["Name"].default_value = "di_tang"
sep = n.new("ShaderNodeSeparateXYZ"); sep.location = (-660, 560)
ang = n.new("ShaderNodeMath"); ang.location = (-480, 560); ang.operation = 'ARCTAN2'
L(tang.outputs[0], sep.inputs["Vector"])
L(sep.outputs["Y"], ang.inputs[0])
L(sep.outputs["X"], ang.inputs[1])

join = n.new("GeometryNodeJoinGeometry"); join.location = (860, 0)

def branch(rows, step_mm, z0_mm, twist0, source, y):
"""один участок: rows копий с шагом step_mm, начиная с глубины z0_mm"""
dup = n.new("GeometryNodeDuplicateElements"); dup.location = (-620, y)
dup.domain = 'POINT'
dup.inputs["Amount"].default_value = rows
L(sna.outputs["Geometry"], dup.inputs["Geometry"])

```
mz = n.new("ShaderNodeMath"); mz.location = (-440, y - 180); mz.operation = 'MULTIPLY_ADD'
mz.inputs[1].default_value = -mm(step_mm)
mz.inputs[2].default_value = -mm(z0_mm)
L(dup.outputs["Duplicate Index"], mz.inputs[0])

off = n.new("ShaderNodeCombineXYZ"); off.location = (-260, y - 180)
L(mz.outputs[0], off.inputs["Z"])

sp = n.new("GeometryNodeSetPosition"); sp.location = (-80, y)
L(dup.outputs["Geometry"], sp.inputs["Geometry"])
L(off.outputs["Vector"], sp.inputs["Offset"])

tw = n.new("ShaderNodeMath"); tw.location = (100, y + 240); tw.operation = 'MULTIPLY_ADD'
tw.inputs[1].default_value = math.radians(TWIST_DEG)
tw.inputs[2].default_value = math.radians(twist0)
L(dup.outputs["Duplicate Index"], tw.inputs[0])

add = n.new("ShaderNodeMath"); add.location = (280, y + 240); add.operation = 'ADD'
L(ang.outputs[0], add.inputs[0])
L(tw.outputs[0],  add.inputs[1])
cmb = n.new("ShaderNodeCombineXYZ"); cmb.location = (440, y + 240)
L(add.outputs[0], cmb.inputs["Z"])
e2r = n.new("FunctionNodeEulerToRotation"); e2r.location = (600, y + 240)
L(cmb.outputs["Vector"], e2r.inputs["Euler"])

obj = n.new("GeometryNodeObjectInfo"); obj.location = (440, y - 260)
obj.transform_space = 'ORIGINAL'
obj.inputs["Object"].default_value = source
obj.inputs["As Instance"].default_value = True

iop = n.new("GeometryNodeInstanceOnPoints"); iop.location = (700, y)
L(sp.outputs["Geometry"], iop.inputs["Points"])
L(obj.outputs["Geometry"], iop.inputs["Instance"])
L(e2r.outputs[0], iop.inputs["Rotation"])
L(iop.outputs["Instances"], join.inputs[0])
```

# синяя зона — примитивы, сверху вниз

branch(prim_rows, PRIM_ROW_MM, 0.0, 0.0, prim, 300)

# красная зона — fancy, продолжает с той же точки и с накопленным твистом

branch(fancy_rows, FANCY_ROW_MM, prim_rows * PRIM_ROW_MM,
prim_rows * TWIST_DEG, fancy, -400)

L(join.outputs[0], gout.inputs[0])

md = curve.modifiers.get(MOD_NAME)
if md:
curve.modifiers.remove(md)
md = curve.modifiers.new(MOD_NAME, 'NODES')
md.node_group = ng

print(f"OK: зона prim {zone_mm:.0f} мм = {prim_rows} рядов x {PRIM_ROW_MM} мм | "
f"fancy {fancy_rows} рядов x {FANCY_ROW_MM} мм")
