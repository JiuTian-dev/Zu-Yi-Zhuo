---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: a6cc81b1715172b477c70fb5d7fbe175_1db045b4acc511f18039525400461939
    ReservedCode1: vuIQOdPx2+d8KnbYoLJk0X77ba48S5R0e0uXEg1/NC4U6OUW/c5GIiDeIm0lWhsVTZ9dL7P1ZfLOEh1Y8UqstTbEsewaZtd3m/f5QIY8/UN3zKYdQt49CHi8op0eV2YhnG8QZf9qlPPnyis8jm7CZ2VzGgxt7YnMtlviKnWEwWT4lRUDoL/HQZ1Qtkk=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: a6cc81b1715172b477c70fb5d7fbe175_1db045b4acc511f18039525400461939
    ReservedCode2: vuIQOdPx2+d8KnbYoLJk0X77ba48S5R0e0uXEg1/NC4U6OUW/c5GIiDeIm0lWhsVTZ9dL7P1ZfLOEh1Y8UqstTbEsewaZtd3m/f5QIY8/UN3zKYdQt49CHi8op0eV2YhnG8QZf9qlPPnyis8jm7CZ2VzGgxt7YnMtlviKnWEwWT4lRUDoL/HQZ1Qtkk=
---

# 首页素材就位清单（home）

更新时间：2026-09-10
素材根目录：`public/assets/home/`

## 一、已就位素材

### hdri/ 环境光照（Poly Haven，CC0）
| 文件 | 规格 | 用途 |
| --- | --- | --- |
| `hdri/evening_road_01/evening_road_01_2k.hdr` | 2K HDR | 黄昏环境光 + 天空盒，日落方向确定主光朝向 |

### ground/ 地面贴图（Poly Haven，CC0，2K JPG）
| 资产 | 包含贴图 | 用途 |
| --- | --- | --- |
| `ground/asphalt_03/` | diff / nor_gl / rough | 街道沥青路面 |
| `ground/asphalt_06/` | diff / nor_gl / rough | 停车场地面 |

### buildings/ 建筑（Kenney City Kit Commercial 2.1，CC0）
- 中层建筑：`building-a.glb` ~ `building-n.glb`（14 个）
- 摩天楼：`building-skyscraper-a.glb` ~ `-e.glb`（5 个）
- 远景低模体块：`low-detail-building-a.glb` ~ `-n.glb` + `-wide-a/b.glb`（16 个）
- 共用贴图：`buildings/textures/colormap.png`

### props/ 街道道具（Kenney City Kit Roads，CC0）
- 路灯：`light-curved*.glb`、`light-square*.glb`（6 个）
- 电杆电线：`electricity-pole*.glb`、`electricity-side*.glb`、`electricity-wires*.glb`（8 个）
- 信号灯：`traffic-light*.glb`（5 个）
- 路面模块：`road-straight / crossroad / intersection / curve / side / end / driveway-single / split` 等
- 地块：`tile-low.glb`、`tile-high.glb`
- 杂项：`dumpster.glb`、`construction-*.glb`、`road-sign-*.glb`、`sign-highway*.glb`
- 写实路灯：`street_lamp_01/`（Poly Haven，CC0，含 gltf + 3 张贴图）

### trees/ 植被（Kenney Nature Kit 2.1，CC0）
`tree_oak / tree_default / tree_detailed / tree_tall / tree_small / tree_thin / tree_fat / tree_pineTallA / tree_pineRoundA / tree_plateau`、`plant_bush*`、`grass*`、`rock_smallA`、`rock_largeA`

### vehicle/ 车辆外观（Kenney Car Kit 3.1，CC0）
`sedan / sedan-sports / suv / suv-luxury / hatchback-sports / van / taxi / truck / delivery / police`、`wheel-default / wheel-dark`

## 二、仍缺（需 AI 生成，尚未产出）

| 占位文件名 | 目标路径 | 规格 |
| --- | --- | --- |
| `home-car-body.glb` | `vehicle/` | 车外观，≤30k 面 |
| `home-cockpit.glb` | `vehicle/` | 车内驾驶位（仪表台/方向盘/中置后视镜/左前窗框），≤20k 面 |
| `home-building-tower-a.glb` | `buildings/` | 主写字楼，≤5k 面 |
| `home-building-tower-b.glb` | `buildings/` | 副楼，≤3k 面 |
| `home-sign-board.glb` | `props/` | 出口立牌（待定） |

注：`vehicle/` 下的 Kenney 整车可先充当车外观临时替代，但**车内驾驶位必须 AI 生成**，且两者需同车型同比例。

## 三、命名与使用约定

- 自产素材一律小写 kebab-case，前缀 `home-`；贴图后缀统一 `-basecolor / -normal / -roughness / -emissive`
- 第三方包内文件名保持原样（GLB 内部引用路径不可改）
- 引擎内统一走相对路径 `assets/home/...` 加载

## 四、清理记录

- 2026-09-10：移除 Poly Haven 写实高模树 `fir_tree_01`（456 MB）、`tree_small_02`（91 MB），改用 Kenney 低模树，节省约 547 MB

## 五、来源与许可

| 来源 | 许可 | 说明 |
| --- | --- | --- |
| Poly Haven | CC0 | HDRI、沥青贴图、写实路灯 |
| Kenney（经 OpenGameArt 分发） | CC0 | 建筑、道路道具、车辆、植被 |

均为 CC0，可商用，署名非强制。
*（内容由AI生成，仅供参考）*
