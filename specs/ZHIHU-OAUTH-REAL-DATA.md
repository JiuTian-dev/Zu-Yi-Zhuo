# 知乎 OAuth 与真实数据接入清单

更新时间：2026-09-04

## 目标

让“组一桌”用知乎官方授权完成两件事：

1. 识别当前用户，并把前端临时 `guest-*` 身份替换成可信服务端会话。
2. 在用户明确授权后，把本人创作、关注和收藏转成后端已有的个人上下文信号；公开内容搜索继续服务于问题发现、匹配理由和讨论 Grounding。

不使用 Cookie 抓取、页面爬虫或前端直传 token。

## 已确认的官方契约

- 通用数据 API 使用开放平台 `Access Secret`，通过 `Authorization: Bearer ...` 和秒级 `X-Request-Timestamp` 鉴权。
- 第三方 Web 应用使用 OAuth 2.0 Authorization Code Flow。授权地址为 `https://openapi.zhihu.com/authorize`，回调参数名为 `authorization_code`，换 token 地址为 `https://openapi.zhihu.com/access_token`。
- `app_key`、授权码交换和 OAuth token 使用必须发生在服务端。
- 读取授权用户的创作、关注和收藏时，请求仍需携带应用的 `Access Secret`，并额外通过 `X-OAuth-Token` 携带该用户的 OAuth token。
- 当前 OAuth token 示例有效期为 3600 秒。

官方文档入口：

- `https://developer.zhihu.com/docs?key=zhihu_oauth_integrated`
- `https://developer.zhihu.com/docs?key=zhihu_search`
- `https://developer.zhihu.com/docs?key=user_contents`
- `https://developer.zhihu.com/docs?key=user_followees`
- `https://developer.zhihu.com/docs?key=user_collections`

## 当前仓库状态

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| 公开知乎搜索 | 可接凭据 | `backend/adapters/zhihu_source.py` 已把官方搜索结果归一化为 `ContentSignal` / `ParticipantSeed`；本轮已对齐官方 `Count` 参数和单次 10 条上限 |
| 单账号本人数据 | 可做联调 | 使用服务端 `Access Secret` + `ZHIHU_PERSONAL_VIEWER_ID` 可验证本人创作、关注、收藏；只允许绑定的一个 viewer，不能冒充其他用户 |
| 多用户 OAuth | 服务端协调器已接入，待凭据联调 | 申请邮件已经发出，但仓库和本机均没有 `app_id` / `app_key` / `Access Secret` |
| 前端身份 | 开发态 + 服务端会话已就绪 | `src/live/identity.ts` 仍生成会话级 `guest-*`；API 请求已携带 Cookie，前端身份 hydration 还未替换 |
| 后端身份校验 | 已接入可选真实会话 | OAuth 配置启用后，服务端会话解析器同时覆盖自作用域 REST 与参与者 WebSocket；显式注入的 resolver 优先 |
| OAuth 回调 | Pages 中继 + FastAPI coordinator 已接入 | `functions/auth/callback.js` 只转发允许字段；FastAPI 负责 state、换 token、加密落库和会话，不接触前端 token |
| 个人数据产品接口 | 已具备 | consent、personal-context preview、匹配、Grounding、replay 等后端契约已经存在 |

## 解决顺序

### O0：现在已经完成

- [x] 核对知乎官方 OAuth、搜索和用户数据接口。
- [x] 修正搜索适配器：`Limit` 改为官方 `Count`，单次请求上限改为 10。
- [x] 本人公开创作改用 `ContentType=all`，再按产品领域类型做显式过滤，补回“问题”类型。
- [x] 为适配器补充无密钥 fail-closed、请求头隔离、参数和账号隔离测试。
- [x] 把 `httpx` 写入后端正式依赖。
- [x] 把 `cryptography` 写入后端正式依赖，供服务端加密 OAuth token。
- [x] 增加 Cloudflare Pages 回调中继，并把 `.dev.vars*` 纳入忽略列表。

### O1：拿到开放平台 Access Secret 后，当天可完成

- [ ] 把 `ZHIHU_ACCESS_SECRET` 写入后端部署平台的加密 Secret，不写 `.env`、Pages 明文变量或 GitHub。
- [ ] 用 `/api/v1/quota?APIIDs=zhihu_search,user_data` 做最小鉴权探针。
- [ ] 配置 `CONTENT_SIGNAL_SOURCE_COMMAND` 与 `CANDIDATE_SOURCE_COMMAND` 指向仓库内适配器。
- [ ] 用真实关键词跑 `POST /opportunities/source-preview`，检查标题、摘要、作者、来源 URL 和数量边界。
- [ ] 仅为申请账号配置 `ZHIHU_PERSONAL_VIEWER_ID`，跑一次创作/关注/收藏 smoke；该模式只用于 OAuth 获批前的单账号联调。

### O2：服务端 OAuth coordinator（主体已完成，待知乎凭据联调）

- [ ] 将 `app_id` 作为服务端配置、`app_key` 作为加密 Secret 注入；二者都不进入 Vite 变量。
- [x] 部署前可用的 OAuth coordinator 已落到 `backend/app/auth/zhihu.py`：创建授权尝试、跳转知乎、校验回调、服务端换 token、建立 HttpOnly 会话、退出与删除本地连接。
- [ ] Pages 设置 `ZHIHU_OAUTH_BACKEND_CALLBACK_URL=https://<api-domain>/auth/zhihu/callback`；这个配置不是 secret。
- [x] 后端会话 cookie 使用 `Secure + HttpOnly + SameSite=Lax`；启用 OAuth 时 CORS 自动开启 credentials，生产仍需把 `CORS_ORIGINS` 收紧为正式 Origin。
- [x] OAuth token 只以 Fernet 加密形式保存在服务端 SQLite，记录过期时间；日志、错误、URL、前端状态、回放和桌状态均不得出现 token。
- [x] `identity_resolver` 从服务端会话解析内部 participant id，OAuth 配置启用后 REST/WebSocket 不再信任前端自报 `guest-*`。
- [x] 新增 `GET /auth/zhihu/start`、`GET /auth/zhihu/callback`、`GET /auth/session`、`POST /auth/logout`、`POST /auth/zhihu/disconnect`；未配置四项 OAuth 核心变量时整组路由不注册。

当前 coordinator 的内部 `participant_id` 是服务端生成的会话主体（`session-*`）。知乎官方当前公开文档没有稳定用户信息接口和用户 ID 字段，因此 O2 暂不把它误称为知乎账号 ID；拿到官方确认后在 O3 补上账号主体绑定。

### O3：把授权用户数据接进现有产品链

- [ ] OAuth gateway 按 viewer 查找 token，并调用用户数据 API：应用 `Access Secret` 放 `Authorization`，用户 token 放 `X-OAuth-Token`。
- [ ] gateway 输出后端现有规范化契约，不把知乎原始响应和 token 交给浏览器。
- [ ] “创作 / 关注 / 收藏”分别映射到 `public_content / follows / favorites` consent；默认全关，用户逐项开启。
- [ ] 撤销 consent 后立即停止读取对应 scope；退出账号后删除本地 OAuth 连接和缓存。
- [ ] 匹配理由只引用用户允许展示的结论，原始个人信号继续保持本人可见、默认不落桌状态。

### O4：前端完成态

- [ ] 增加“连接知乎”入口，但只有后端 `/capabilities` 报告 OAuth 已配置时才显示可用状态。
- [ ] 回调成功后读取 `/auth/session`，由服务端返回内部 participant id、显示名和头像投影；当前 endpoint 已能返回会话和连接状态，显示名/头像等待官方用户信息契约。
- [ ] 授权面板清楚列出创作、关注、收藏三个用途；不把“登录”与“同意用于匹配”合并成一次默认授权。
- [ ] token 过期时显示“重新连接知乎”，不静默降级成假资料或另一位用户的数据。

### O5：上线验收

- [ ] 两个知乎账号在两个浏览器分别授权，身份、token、个人信号和 WebSocket 互不串线。
- [ ] 伪造 viewer id 返回 403；无会话返回 401；过期/重复授权码失败且不创建会话。
- [ ] 回调参数不进入访问日志；错误页不回显授权码。
- [ ] token 过期、知乎 401/429/5xx、后端重启、双实例并发都 fail-closed，不回退 mock。
- [ ] 用户撤销 consent、退出和删除连接后，后续个人数据请求不可再成功。

## 仍需向知乎确认

官方当前公开页没有给出以下完整契约，不能靠猜测上线：

1. OAuth 获取用户信息的 URL、返回字段和稳定用户 ID 字段。
2. 授权地址是否支持并原样回传 `state`；如果不支持，知乎推荐的登录 CSRF 防护方式是什么。
3. 是否提供 refresh token、刷新接口、撤销接口；没有 refresh 时是否必须每小时重新授权。
4. 邮箱、手机权限对应的用户信息字段是否默认脱敏，以及它们是否真的需要用于本产品。
5. 回调 URL 是否要求完全匹配，Pages 中继到 API 域名是否在审核范围内。

建议直接回复原申请邮件补问以上五项，并把最终生产 API 域名一并说明。未得到确认前，OAuth 只做“数据连接”联调，不把它宣称为稳定登录系统。

## 部署配置边界

Cloudflare Pages：

```text
ZHIHU_OAUTH_BACKEND_CALLBACK_URL=https://<api-domain>/auth/zhihu/callback
```

后端 Secret（拿到后再配置）：

```text
ZHIHU_ACCESS_SECRET=<encrypted secret>
ZHIHU_APP_ID=<server configuration>
ZHIHU_APP_KEY=<encrypted secret>
ZHIHU_OAUTH_REDIRECT_URI=https://zhihu-knowledge-forge.pages.dev/auth/callback
ZHIHU_OAUTH_ENCRYPTION_KEY=<Fernet key in Secret Manager>
ZHIHU_OAUTH_STORE_PATH=<shared writable SQLite path>
ZHIHU_OAUTH_POST_LOGIN_URL=https://zhihu-knowledge-forge.pages.dev/
# 仅当前端与 API 跨站时启用；必须同时保持 HTTPS + Secure
ZHIHU_OAUTH_COOKIE_SAMESITE=none
CORS_ORIGINS=https://zhihu-knowledge-forge.pages.dev
```

若前端与 API 不在同一站点（例如 Pages 域名和独立 API 域名），Cookie 需要在 HTTPS 下配置 `ZHIHU_OAUTH_COOKIE_SAMESITE=none`；同站点部署保持默认 `lax`。前端请求已固定使用 `credentials: include`，服务端 CORS 不能使用通配符 Origin。

本地生成加密密钥（只把结果放进本机 secret store，不要提交）：

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

任何 `ZHIHU_*SECRET`、`APP_KEY`、OAuth token、`.dev.vars` 和本地 `.env` 都不得提交。
