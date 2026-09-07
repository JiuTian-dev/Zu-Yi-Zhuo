# 远景雪山素材与精细化调研

日期：2026-09-06

## 修订结论：不采用低模雪山或低模云团

用户明确不要低模模型。当前 `DistantLandscape.js` 的规则网格和正弦山脊只能作为占位实现，不能继续作为最终雪山。新的首选路线是：

1. 从真实瑞士山脉的 DEM 高程数据生成山体，保留真实峰谷、山脊和坡面关系。
2. 在 Blender 中做裁切、重拓扑、平滑法线和两级 LOD，再导出压缩 GLB；LOD 只是性能手段，正常机位不能看出多边形切面。
3. 岩石和雪面继续接入 Bruno 的 TSL 光照、调色板、雾和后处理。写实资产提供几何细节与表面法线，不直接把照片式色彩带入场景。
4. 云采用局部体积云和山体高度雾，不再使用低模云块。

推荐先试 **伯尔尼高地 Eiger–Mönch–Jungfrau 山脊**，因为它能形成宽阔、连续且有多个峰肩的远景；Matterhorn 可作为第二个轮廓方案，但单峰过强，容易抢走桌子和瀑布遗迹的注意力。海侧仍保持开放，不让山脉围成一圈。

## 精细化实施标准

### 造型

- 不用一整圈封闭山墙包围桌区；山脉只放在林木侧，海侧保留开口。
- 主峰来自真实高程或高精度雕刻网格，使用不对称峰顶、前后错层和断崖面，避免重复正弦曲线造成“软裙边”。
- 山脚低于近景树冠的视觉重心，峰顶进入远距雾，不与桌、瀑布遗迹抢主视觉。
- 不增加实时碰撞、角色路径或游戏交互；远景只属于渲染层。

### 材质与颜色

- 岩面使用 Bruno 调色板的蓝灰、紫灰和低饱和冷绿；可使用高质量 normal、roughness 和轻量 displacement 保留岩层细节，但不直接使用写实 diffuse。
- 雪线不是整块白色贴片：以高度、法线朝向和低频噪声共同决定，形成断续雪肩和阴面留岩。
- 雪面受昼夜光照，但不投射阴影；通过动态雾和远距颜色混合连接天空，避免远峰变成一张硬剪影。
- 保留现有 `MeshDefaultMaterial` / TSL 链路；纹理使用三平面投影或坡度投影，避免大山体 UV 拉伸，也不能绕开项目雾、光照和后处理。

### 性能

- 桌面高质量山体建议约 60k–120k 可见三角形，并准备约 15k–30k 的远距 LOD；优先保轮廓、法线和雪肩，删掉相机看不到的背面与山脚内部面。
- 主峰默认不启用阴影贴图；用法线、AO、昼夜主光和雾表现体积，避免扩大阴影 atlas。
- 纹理运行时使用 1K–2K KTX2；几何使用 Draco 或 Meshopt 压缩。项目已有 KTX2/Basis 和 Draco 加载链，不增加第二个 renderer。
- 局部体积云先以半分辨率、有限步数运行，并提供静态软云层回退；性能验收以桌内交互帧稳定为先。

## 非低模资源候选与处理方式

| 优先级 | 来源 | 可用内容 | 判断 |
| --- | --- | --- | --- |
| A | [NASA Earthdata NASADEM / SRTM](https://www.earthdata.nasa.gov/centers/lp-daac) | 全球约 30 米高程数据；LP DAAC 说明其分发数据可公开复用 | 最推荐。截取真实瑞士山脉轮廓，在 Blender 中离线生成、清理并导出 GLB |
| A | [BlenderGIS](https://github.com/domlysz/blendergis) | 可导入 GeoTIFF DEM、SRTM 并生成地形网格 | 作为离线生产工具，不进入浏览器依赖；最终仓库只放处理后的山体和来源记录 |
| B | [Poly Haven Mountainside](https://polyhaven.com/a/mountainside) | 288k 三角形、带 LOD 的高精度扫描崖壁，glTF/FBX/USD，CC0 | 可补主峰近侧断崖和岩层细节；必须重拓扑、压缩并改用 Bruno 配色 |
| B | [Sketchfab Snow Mountain](https://sketchfab.com/3d-models/snow-mountain-e42d1a231cf54ff3a01dc691c050762c) | 83.7k 三角形、4K PBR、FBX，CC BY | 可作为高精度轮廓对照或备选山体；需要署名、补 LOD，并验证下载文件后再决定是否进入项目 |
| A | [ambientCG Snow 006](https://ambientcg.com/view?id=Snow006) | 摄影测量雪地材质，1K–8K PBR，CC0 | 只取 normal/roughness/height 细节，颜色由 Bruno TSL 控制 |
| A | [Poly Haven Snow 02](https://polyhaven.com/a/snow_02) | 粉雪材质，含 bump/displacement/normal/roughness，CC0 | 适合雪肩和缓坡；运行时只保留压缩后的 1K–2K 必要贴图 |

### 可选离线地形工具

- [Gaea](https://www.quadspinner.com/Download) 能导出高度场和网格，适合在真实 DEM 上补侵蚀、断崖和积雪遮罩；但 Community Edition 仅限评估和非商业使用，不能作为最终可商用资产流程的默认工具。
- [World Machine Basic](https://www.world-machine.com/download.php) 也能生成侵蚀和 PBR 地形，但免费版同样是非商业用途且输出限制在 1025×1025。除非确认比赛和后续产品的许可边界，否则不采用其输出。
- 因此首轮应使用 NASADEM/SRTM + BlenderGIS/Blender；数据、工具和最终模型三者的许可分别记录。

## 本轮已完成的时间控制

- 自动昼夜从 4 分钟一轮调整为 8 分钟一轮。
- 场景设置新增：自动变化、一直白天、一直黑夜。
- 固定模式使用稳定的昼/夜平台进度，不会停在黄昏过渡帧。
- 选择写入浏览器本地存储，仅影响当前设备的视觉偏好，不写入后端桌状态，也不影响其他参与者。

## 非低模云雾路线

### 首选：局部 WebGPU 体积云 + 山体高度雾

Three.js 官方已有 [Volumetric Cloud](https://threejs.org/examples/webgpu_volume_cloud.html)、[Fog Scattering](https://threejs.org/examples/webgpu_custom_fog_scattering.html) 和 [Height Fog](https://threejs.org/examples/webgpu_fog_height.html) 示例。它们与项目正在使用的 WebGPU/TSL 技术方向一致，适合拆出三个能力：

1. **山脚高度雾**：贴着林线和山谷流动，使用世界高度、深度和噪声控制密度，不覆盖桌边近景。
2. **山腰局部体积云**：只在两个或三个有限包围盒内 raymarch，形成柔软、连续、有内外明暗的云层；不做几何云块。
3. **峰顶薄云**：低密度体积层穿过雪肩，让山峰偶尔显隐，漂移周期明显慢于树叶、水面和昼夜变化。

云色继续由 `DayCycles` 驱动：白天为偏冷暖白，黄昏吸收粉紫环境色，夜间只保留低亮度蓝紫散射。第一版不做实时云影，避免桌面亮度跳动；高质量档稳定后再评估只投向山体的低频云影。

### VDB 和现成云资产的判断

- [OpenVDB](https://www.openvdb.org/download/) 提供高分辨率体积样例，但单个样例通常从数十 MB 起；Disney 的公开云数据压缩包约 3 GB。它们适合离线研究密度形状，不适合直接作为网页运行时资产。
- 如果要利用 VDB，只应在 Blender/Houdini 中离线降采样并烘焙成小型 3D density texture 或切片图集，再由 TSL 采样；运行时不引入 VDB 解析器。
- [Poly Haven Fouriesburg Mountain Cloudy HDRI](https://polyhaven.com/a/fouriesburg_mountain_cloudy) 可作为云色、远景对比度和散射参考，但不能替换当前天空，也不能提供可穿行的局部山雾。
- `@yong_three/three-clouds` 功能完整，但当前公开版本目标是 Three.js 0.184.x，并需要额外 atmosphere、深度合成和较高纹理采样上限；当前项目是 0.183.2，暂不安装，避免为了远景云层重做 Bruno 的 RenderPipeline。

### 最终推荐组合

| 层级 | 数据/资产 | 运行时表达 |
| --- | --- | --- |
| 山体轮廓 | NASADEM/SRTM 瑞士山脉 DEM | 平滑高精度 GLB，两级 LOD，海侧开放 |
| 岩壁细节 | Poly Haven Mountainside 或 DEM 后的 Blender 雕刻 | Bruno TSL 配色 + 压缩 normal/roughness |
| 积雪细节 | ambientCG Snow 006 / Poly Haven Snow 02 | 高度、坡度、噪声遮罩 + 1K–2K KTX2 法线/粗糙度 |
| 山谷雾 | Three.js Height Fog / Scattering 思路 | 当前场景内的局部 TSL 密度函数 |
| 山腰和峰顶云 | Three.js Volumetric Cloud 思路 | 有限体积包围盒、半分辨率、质量分档 |

## 下一步实施顺序

1. 用 NASADEM/SRTM 截取两套候选山脊：Eiger–Mönch–Jungfrau 宽山脊和 Matterhorn 单峰，导入 Blender 生成不带材质的高精度灰模。
2. 放进当前场景做纯构图 A/B：检查山侧过渡、海侧开口、桌面视觉权重和 34 米远距机位；先定轮廓，再做材质。
3. 给胜出山体加入 TSL 三平面岩层、断续雪线和压缩雪面 normal/roughness；不使用原始照片 diffuse。
4. 在山体包围盒中加入高度雾，再加一个局部体积云原型；分别测试白天、夜间和自动昼夜。
5. 完成后才移除 `DistantLandscape.js` 当前正弦占位山脊。验收前保留旧实现作为可切换对照，避免再次出现改完无法回看基准。

## 验收标准

- 正常桌内和最远 34 米机位看不到明显多边形切面、规则波浪峰或贴片云。
- 山体有真实山谷、峰肩、雪沟和阴阳坡；细节不会被一层纯白雪色抹平。
- 云有柔软边缘、内部明暗和缓慢形变，能穿过山肩但不穿帮到桌面近景。
- 桌、桥、瀑布遗迹、樱花树始终是近景主角；雪山和云雾负责扩大世界，不成为新的交互物。
- WebGPU 高质量档和回退档都保持单 Canvas；场景设置仍只控制视觉状态，不写入后端桌状态。

## 素材准备状态（2026-09-07）

- 已准备真实高程源：Matterhorn 附近的 `N45E007`，以及 Eiger–Mönch–Jungfrau 附近的 `N46E007`、`N46E008`，本地源文件位于被忽略的 `3D/alpine-source/dem/srtm/`。
- 已准备高质量候选：Poly Haven Mountainside 2K glTF、Poly Haven Snow 02 2K 材质、ambientCG Snow 006 1K 材质，运行时候选位于 `public/assets/bruno-runtime/alpine/`。
- 已核对 Mountainside glTF 的 buffer 和三张纹理引用，文件结构可直接被 GLTFLoader 读取；目前只作为候选，不自动挂到场景，避免未经构图验收就改变当前画面。
- 云雾不引入外部低模模型；后续直接在现有 WebGPU/TSL 管线中做局部体积云和山体高度雾。
- 资产来源、许可证、目录和下一步处理记录见 `docs/ALPINE-ASSET-PREP-2026-09-07.md` 及 `public/assets/bruno-runtime/alpine/README.md`。
