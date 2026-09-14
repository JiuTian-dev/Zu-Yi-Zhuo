---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: a6cc81b1715172b477c70fb5d7fbe175_e22396eeacc111f1af37525400826444
    ReservedCode1: MskgVSwyFWdWIerBHdLLbxFcWcNg1lbU4eTbL7EnNi4Maqew0JPW0XX0+gNLHfg73R8xUXSsSe649FUD9G2X85+/C/k/465Ma19/h2uMdju1E+dZVNdBGrSXkSrNUvDfT1FDdpJPWhttG0N6qg/IzqvzqhCGchLjuX0+VqnKmLYABrVPWxiSxTKBaCc=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: a6cc81b1715172b477c70fb5d7fbe175_e22396eeacc111f1af37525400826444
    ReservedCode2: MskgVSwyFWdWIerBHdLLbxFcWcNg1lbU4eTbL7EnNi4Maqew0JPW0XX0+gNLHfg73R8xUXSsSe649FUD9G2X85+/C/k/465Ma19/h2uMdju1E+dZVNdBGrSXkSrNUvDfT1FDdpJPWhttG0N6qg/IzqvzqhCGchLjuX0+VqnKmLYABrVPWxiSxTKBaCc=
---

# 素材清单

## 1. 落地约定

### 1.1 目录

```
public/assets/home/
├── hdri/          # 环境贴图
├── env/           # 地形、天际线
├── buildings/     # 写字楼
├── ground/        # 可平铺地面贴图
├── props/         # 路灯、立牌
├── trees/         # 树
└── vehicle/       # 车（外观）
```

### 1.2 命名规范

- 全小写 kebab-case，统一前缀 `home-`
- 贴图后缀固定：`-basecolor` / `-normal` / `-roughness` / `-emissive`
- 例：`home-tree-a.glb`、`home-parking-basecolor.png`

### 1.3 来源优先级

1. CC0 / 免费商用素材站（Poly Haven、Quaternius、Kenney）
2. AI 生成（车、楼、立牌 —— 这些需要贴合构图，通用库里找不到合适的）
3. 程序化生成（地形、远景体块）

## 2. 资产明细

### A. 环境

| # | 资产 | 用途 | 来源 | 规格 | 文件名 |
|---|---|---|---|---|---|
| A1 | 黄昏 HDRI | 环境光 + 背景天空 | Poly Haven（CC0） | 2K HDR，**不要 4K**（省显存） | `home-sky-dusk.hdr` |
| A2 | 城市天际线体块 | 远景天际线 + 承担「城市缩小」（`driving` 段后移淡出） | CC0 低模 / 程序化 | 合计 ≤ 10k tris | `home-city-skyline.glb` |
| A3 | 丘陵地形 | 旷野段远景与地面 | 程序化 / CC0 | 大面积几何，靠雾遮远 | `home-terrain-hills.glb` |

### B. 建筑与街道

| # | 资产 | 用途 | 来源 | 规格 | 文件名 |
|---|---|---|---|---|---|
| B1 | 写字楼主楼 | 画面右侧，「公司」的交代 | AI 生成 | ≤ 5k tris，玻璃幕墙 | `home-building-tower-a.glb` |
| B2 | 写字楼副楼 | 左侧远景 | AI 生成 / CC0 | ≤ 3k tris | `home-building-tower-b.glb` |
| B3 | 停车场地面贴图 | 楼下停车场，**含车位线** | CC0（可平铺） | 2048²，含 normal | `home-parking-basecolor.png` |
| B4 | 街道路面贴图 | 三层结构中的近景路面 | CC0（可平铺） | 2048²，含 normal | `home-road-basecolor.png` |
| B5 | 路灯 | 黄昏氛围 | CC0 | 2–3 根，低模 | `home-streetlamp.glb` |
| B6 | 出口立牌 | 第二入口（**待定**） | AI 生成 | 独立模型，便于挂交互 | `home-sign-board.glb` |

### C. 自然

| # | 资产 | 用途 | 来源 | 规格 | 文件名 |
|---|---|---|---|---|---|
| C1 | 树 · 3 种 | 中景立牌 + 旷野段 | Quaternius（CC0） | 单株 ≤ 2k tris，`InstancedMesh` | `home-tree-a/b/c.glb` |
| C2 | 草簇 / 灌木 | 旷野段点缀（可选） | Quaternius（CC0） | 极低模 | `home-bush-a.glb` |

### D. 车辆

| # | 资产 | 用途 | 来源 | 规格 | 文件名 |
|---|---|---|---|---|---|
| D1 | 车外观 | `idle` 至 `outro` 全程可见（车外第三人称跟车） | AI 生成 | ≤ 30k tris，含车门缝、轮毂 | `home-car-body.glb` |

> D1 是全程唯一车辆资产：车尾与后 3/4 视角形面必须完整、**尾灯可辨**，四个车轮为独立节点（`wheel_fl/fr/rl/rr`）供 `driving` 段旋转。车内不做任何资产。

### E. 贴图与材质

| # | 资产 | 说明 |
|---|---|---|
| E1 | 车身材质 | 深色车漆，清漆反射 |
| E2 | 玻璃材质 | 车窗，透光 + 轻微反射 |

## 3. 素材获取方式备注

- **Poly Haven**：`https://polyhaven.com` — HDRI 全 CC0，直接下 2K
- **Quaternius**：`https://quaternius.com` — 低模自然资产包，CC0
- **Kenney**：`https://kenney.nl` — 低模道具与城市件，CC0
- **AI 生成**：Tripo / Meshy / Rodin 任选，导出 GLB，注意压面数与烘焙贴图

## 4. 配置数据（非素材，但需一并产出）

实现时需产出两份配置，便于调参不改代码：

### `config/sceneryStages.ts`

三段沿途的配置，每段包含：

```ts
{
  id: 'city' | 'suburb' | 'wild',
  timeRange: [start, end],        // 相对 driving 段的起止
  horizonAsset: string,           // 远景用哪份资产
  props: string[],                // 中景立牌资产清单
  scrollSpeed: number,            // 近景滚动速度系数
  parallaxFactor: number,         // 中景视差系数
  fogDensity: number,
}
```

### `config/departureTimeline.ts`

全部关键时间点（见 `02-timeline-and-fallbacks.md` 第 2 节），单文件集中定义。

## 5. 交付检查

- [ ] 所有 GLB 面数在预算内
- [ ] 贴图尺寸不超过 2048²（HDRI 除外）
- [ ] 命名与目录符合 1.1 / 1.2
- [ ] D1 车尾与后 3/4 视角完整、尾灯可辨，四轮为独立节点且原点在车底中心
- [ ] 每份资产在页面里实际加载过，无 404
*（内容由AI生成，仅供参考）*
