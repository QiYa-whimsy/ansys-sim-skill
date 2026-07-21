# ansys-sim（中文说明）

[English README](README.md)

一个用于 Claude Code / Claude Agent 的 skill，通过 PyAnsys（`ansys-mechanical-core`
即 PyMechanical、`ansys-mapdl-core` 即 PyMAPDL、`ansys-dpf-post` 即 PyDPF-Post）
自动化驱动 ANSYS Workbench 结构仿真，替代手动 GUI 操作。

## 能做什么

- 编写/调试驱动 Mechanical 对象模型（PyMechanical）或 APDL 命令级求解
  （PyMAPDL）的 Python 脚本。
- 静力结构、模态、谐响应、随机振动、瞬态结构、**显式动力学（跌落/冲击测试）**、
  疲劳分析。
- 跨材料/载荷/几何变量的批量参数扫描（DOE）。
- 用 PyDPF-Post 提取应力/应变/位移/频率/模态结果，生成图表、云图或
  Word/Excel/PDF 仿真报告。

## 安装

```bash
npx skills add <owner>/ansys-sim-skill
```

或者直接把仓库内容克隆/复制到你的 skills 目录下（例如
`~/.claude/skills/ansys-sim`）。

## 目录结构

- `SKILL.md` —— 调度入口：什么时候用这个 skill、默认假设、必经工作流、
  不可妥协的底线，以及指向 `references/` 各文件的触发条件。
- `references/` —— 按主题拆分的详细操作指南（环境搭建、静力结构、动力学分析、
  显式动力学/冲击、疲劳与参数扫描、后处理与报告、故障排查），只在对应场景才
  加载，避免上下文臃肿。
- `scripts/` —— 真正可复用的 CLI 工具：许可证/会话诊断
  （`session_check.py`）、接触/冲击类分析的求解前体检工具
  （`preflight_check.py`）、参数扫描调度器（`sweep_runner.py`）、报告生成器
  （`report_builder.py`）。

## 这个 skill 里沉淀的真实教训

以下所有例子都来自这个 skill 打磨过程中实际执行的一个项目：对一个钣金
外壳零件做冲击测试仿真（Explicit Dynamics / AUTODYN 求解器），判断结构
最薄弱面在给定冲击能量下是否会开裂、凹陷。为避免泄露具体项目/产品信息，
下面把真实文件名替换成了通用占位名（`target.stp`/`impactor.stp`），把
具体求解数值替换成了量级描述，但每一条坑本身、每一个报错信息都是真实
遇到过的，不是从文档推测的。

### 1. "求解成功"不代表结果有效——全零结果的陷阱

这是本项目最贵的一次教训。冲击物的 `Velocity` 载荷最初按照对几何朝向的
一个过时假设设成了 `-Z` 方向，但冲击物的实际包围盒其实在目标面 **下方**
沿 Z 方向存在一个小间隙——它需要往 `+Z` 方向运动才能真正撞上目标面。

结果是：`ed.Solve(True)` 顺利返回，`Solution.ObjectState` 显示
`Solved`，`Solution.Status` 显示 `Done`，没有任何异常或警告——但变形、
应力、应变全部三个结果对象的 `Maximum`/`Minimum` 都精确等于 `0`。整个
求解过程在这个项目的网格规模下每次要跑超过一小时，而且跑了**两次**才
发现方向搞反了，白白浪费了两个多小时的真实许可证时间。

**这就是为什么 `scripts/preflight_check.py` 存在**——用几秒钟的几何导入
（不建网格、不求解）去检查速度方向是否真的指向目标体：

```bash
python scripts/preflight_check.py direction \
  --target target.stp \
  --mover impactor.stp \
  --velocity 0 0 1
```

真实输出形态（修正方向之后，数值已改为示意）：

```
Mover centroid:  (x, y, z)
Target centroid: (x, y, z)
Direction mover->target (unit): (~0, ~0, ~1)
Configured velocity direction (unit): (0.0, 0.0, 1.0)
Dot product: 0.9998
PREFLIGHT PASS: velocity points toward the target (dot=0.9998 > 0.05).
```

对于耗时更长的求解，还可以先跑一次短时长的 pilot（比如完整时长的 5%），
确认已经有非零响应再放心跑全程：

```bash
python scripts/preflight_check.py pilot \
  --template solve_run.py \
  --full-end-time-s 0.002 \
  --pilot-fraction 0.05
```

### 2. Explicit Dynamics 必须显式设置线性单元

`mesh.ElementOrder` 默认是 `ProgramControlled`，在这个项目里一度悄悄选用
了二次单元，导致求解设置阶段（而不是建网格阶段）才报错：
`Too many nodes per element. Error reading in the CAERep from
Simulation. Failed.` 建网格之前必须显式指定：

```python
from Ansys.Mechanical.DataModel.Enums import ElementOrder
mesh.ElementOrder = ElementOrder.Linear
```

### 3. Velocity 载荷分量不能直接赋值

`vel.ZComponent = ...` 是只读属性会直接报错；
`vel.ZComponent.Output.SetDiscreteValue(...)` 也会报类型错误或
`NullReferenceException`。真正可行的写法是给 `.Output.DiscreteValues`
赋一个**列表**：

```python
unit_str = str(vel.ZComponent.Output.Unit)
vel.XComponent.Output.DiscreteValues = [Quantity(0.0, unit_str)]
vel.YComponent.Output.DiscreteValues = [Quantity(0.0, unit_str)]
vel.ZComponent.Output.DiscreteValues = [Quantity(v_mm_s, unit_str)]
```

冲击速度通常按冲击能量反算：`v = sqrt(2*E/m)`（`E` 为冲击能量，`m` 为
假设的冲击物质量），务必把这个假设（冲击物质量的来源）在报告里写清楚，
不要当成已知量悄悄用掉。

### 4. 多几何体导入后没有 `.BoundingBox` 属性

同时导入目标体和冲击物两个独立 STEP 文件后，`Body`/`GeoBodyWrapper`
对象**没有** `.BoundingBox`/`.MinX` 这类便捷属性——本项目中用来判断两者
是否真的对齐、判断速度方向的包围盒/质心，都是手动遍历
`body.GetGeoBody().Vertices` 累加 `.X`/`.Y`/`.Z` 算出来的。

### 5. 云图导出发虚——`CurrentGraphicsDisplay` 渲染 bug

`GraphicsImageExportSettings.CurrentGraphicsDisplay` 默认是 `True`，
在没有真实显示缓冲区的 embedded/批处理会话里，导出的云图会变成一张近似
全黑面板上散落着稀疏彩色像素点，而不是平滑的应力/变形云图——但文件依然
"成功"生成，图例、最大最小值和单位都是对的，很容易误以为是结果问题而
不是导出设置问题。

诊断技巧：先比较文件大小。发虚的导出文件在本项目中大小异常稳定，不管怎么
调 `ShowMesh`/`AcceleratedGraphics` 都几乎不变；修复后的正常导出文件大小
会跳升好几倍，且随图像内容变化。修复方式：

```python
settings = GraphicsImageExportSettings()
settings.CurrentGraphicsDisplay = False   # 真正的修复点
settings.Width = 1920
settings.Height = 1080
settings.Resolution = GraphicsResolutionType.HighResolution
```

### 本项目求解结果的量级（示意，非具体项目数据）

| 项目 | 量级 |
|---|---|
| 网格规模 | 约 6 万节点 / 16 万单元（线性单元） |
| 求解步长终止时间 | 毫秒级（典型冲击接触持续时间） |
| 单次全程求解耗时 | 1-3 小时真实许可证时间 |
| 最大等效应力 | 与材料屈服强度同量级——需要和材料数据对照判断是否超限 |
| 最大等效塑性应变 | 非零但很小——需结合材料延伸率判断是否达到失效 |

（这些是量级描述，不是具体项目的真实数值——每个项目的几何、材料、载荷
都必须重新建模、重新求解、重新判断，不能直接套用。）

## 使用这个 skill 的其他真实教训（详见 `references/`）

- `MaterialAssignment.Location`（以及任何 `SelectionInfo.Entities`）必须
  传入 `body.GetGeoBody()` 返回的底层几何对象，直接传 `Body` 包装器会抛
  `InvalidCastException`。
- 想只在冲击区保留细网格、其余区域用 `FeatureSuppress` 粗化——本项目试了
  5 种不同的 scoping 方式全部失败，报错"网格控制没有关联到任何几何结构"。
  务实的默认做法是先用统一网格尺寸，除非节点数真的多到求解不可接受。
- `model.Project.UnitSystem` 这个看起来很合理的调用实际上不存在
  （`AttributeError`），正确写法是 `app.ExtAPI.Application.ActiveUnitSystem`。
- DPF-Post 无法读取 AUTODYN 原生结果格式 `.adres`
  （`DPFServerException: Data sources not defined`），显式动力学分析的
  结果/云图导出要走 Mechanical 自己的 `graphics.ExportImage()`。

这个 skill 的所有指导都来自真实跑过的 PyAnsys 自动化项目，而不是单纯从
文档里推测写出来的——每一条坑都能对应到真实的报错信息或日志行；具体的
产品几何、材料和求解结果数据本身不在此公开仓库中披露。
