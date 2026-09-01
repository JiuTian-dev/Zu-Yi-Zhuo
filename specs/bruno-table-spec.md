# 组一桌 · Bruno 桌场景 Spec（folio-2025 引擎延伸）

> 目标：用 bruno-simon.com/folio-2025 的**源码级渲染系统**（MIT）重建一张圆桌场景，
> 效果与其网站一致。现有 R3F 3D 大改大砍：该桌的 3D 由他的引擎接管。
> 依据源码：D:/folio-2025（MIT），关键文件已在调研中通读。

## 一、复刻原理（从源码读出的配方）

他的画面 = 以下系统的叠加，全部可移植（WebGPURenderer + TSL 节点材质）：

1. **MeshDefaultMaterial**（Materials/MeshDefaultMaterial.js，基于 MeshLambertNodeMaterial）：
   - 颜色来自 **palette.ktx 调色板贴图取样**（NearestFilter，模型 UV 指向调色板位置）
   - **核心阴影**：`dot(N, lightDir).smoothstep(edgeHigh, edgeLow)` 反向分层，混入
     `shadowColor`（非黑色！昼夜变化，如 day=#6d3fff 紫、dusk=#4e009c 深紫）
   - **投影**：shadow map 捕获为 float（catchedShadow），同样混 shadowColor
   - **反弹光**：朝下面按高度衰减混入 terrain.colorNode（地面色反弹）
   - **水邻近**：接近水面高度的面直接变白（岸线泡沫感）
2. **Lighting**：DirectionalLight intensity 5（WebGPU 单位），球坐标由 DayCycles.progress
   驱动（太阳弧线运动），shadow 2048/512 + radius 3 + normalBias 0.1
3. **DayCycles**：day/dusk/night/dawn 四组精确色板（源码 DayCycles.js:5-8），
   progress 在 0-1 循环插值——**他的"感觉"一半来自这些色板**
4. **Fog**：scene.backgroundNode = 屏幕径向双色渐变（fogColorA 中心→fogColorB 边缘），
   材质内 strength = rangeFogFactor(near, far) 混入
5. **Grass**：包裹网格（跟随相机焦点 mod 循环）、每叶 3 顶点（tip+左右）宽度 0.1 高 0.6、
   perlin 高度变化、**始终朝向相机**、风偏移=wind.offsetNode×tipness×height×2、
   颜色=terrain.colorNode、normal=(0,1,0)（草当地面光照，永不发暗）、tip 阴影混合
6. **Wind**：perlin 渲染目标贴图两层采样 → offsetNode
7. **Noises**：perlin 渲染目标（TSL perlinNode 程序化生成）
8. **地面**：Floor 自建 PlaneGeometry + terrainNode 位移/上色（地形网格与数据分离）

## 二、架构（本项目内的落法）

```
src/bruno/                    ← vendored/adapted（保留 MIT 声明 + LICENSE 引用）
  Game-lite.js               ← 极简单例：scene/renderer/canvasElement + 各系统挂载
  Ticker.js / Time.js        ← 原样（71/84 行）
  View-lite.js               ← 只保留 optimalArea{radius,near,far,position}+focusPoint+throttleChange
  Rendering.js               ← 原样（WebGPURenderer + RenderPipeline）
  Ligthing.js                ← 原样（去 debug/Tornado 依赖）
  Cycles/DayCycles.js        ← 原样（progress 固定黄昏 or 缓慢循环）
  Fog.js / Wind.js / Noises.js / Terrain.js ← 原样（tracks 车辙行删除）
  Materials/MeshDefaultMaterial.js ← 原样（reveal 删除/关闭）
  Materials/MeshPaletteMaterial.js ← 新增：我们的调色板 PNG 版本
  World/Floor.js             ← 适配：圆桌草甸盘
  World/Grass.js             ← 原样
  World/TableScene.js        ← 新增：圆桌+五凳+人物+灯笼+花丛（palette 材质）
  shim.js                    ← View/Quality/Debug/Reveal/tracks 的最小桩
static/bruno/                ← palette.png（自绘 16 色调色板，替代 palette.ktx）
BrunoTable.tsx (React)       ← 挂载/卸载引擎 + HUD（复用现有桌内 HUD）
```

- 渲染器：`new WebGPURenderer({ canvas })`（WebGL2 后端自动回退）
- 集成：`坐下来看看`（山谷桌）→ BrunoTable 画布替换现 R3F 世界；桌海入口不变
- 兼容：three 升级到 ^0.183.2（与源码一致）；React 只做挂载，不混渲染层

## 三、场景内容（一张桌）

- 草甸圆盘（terrainNode 数据图：中心草地、外圈湖水渐变）+ Grass 密铺
- 圆木桌（palette 木色）+ 五凳 + 五个坐姿小人（palette 上衣色区分角色）
- 桌上：烛光（emissiveOrangeRadialGradient 火焰材质）+ 杯子
- 灯笼×2（emissivePurple/Orange 渐变）+ 花丛（Flowers）
- 光照：DayCycles **dusk 色板**（#ff8181 光 / #4e009c 影 / 蓝紫雾）缓慢流转
- 相机：固定电影位（焦点=桌面，optimalArea radius≈6）

## 四、执行里程碑

- M1 引导：vendor 核心 12 文件 + palette.png，他的 Grass/Fog/Lighting 在空白草甸上渲染成功（截图）
- M2 建桌：桌/凳/人/道具 palette 材质化， dusk 色板，截图对比 bruno 实机
- M3 集成：替换山谷桌 3D，sea→lobby→bruno 桌全链路
- M4 验收：截图+鼠标测试（hover 岛、点击、拖拽、滚轮、键盘），与 bruno 实机逐项对比，差距即修

## 五、验收标准（对齐 bruno-simon.com）

- [ ] 草海：包裹网格跟随焦点、朝向相机、风摆、地形取色（与他一致）
- [ ] 阴影：有色分层核心阴影 + 投影贴图混 shadowColor（非黑影）
- [ ] 色板：palette 贴图取样或等价色板材质（色彩和谐度一致）
- [ ] 氛围：DayCycles dusk 色板（光/影/雾色与他的源码同值）
- [ ] 交互：鼠标拖拽环视、点击入席、hover 反馈（与现有 HUD 链路一致）
- [ ] 截图对比 bruno 实机：密度/光感/雾感肉眼同族
- [ ] 零 console 错误；构建全绿

## 六、风险与对策

- TSL/三版本漂移：three 锁 ^0.183.2 与源码同版；threejs-override.js 一并 vendor
- WebGPU 不可用：WebGPURenderer 自动回退 WebGL2（源码同机制）
- palette.ktx：用 PNG 调色板替代（NearestFilter 同参数），避免 KTX2 管线
- 版权：MIT，保留 license.md 与来源注释（src/bruno/LICENSE.md）
