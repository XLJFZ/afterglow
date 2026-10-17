# 气象平台比较

调研日期：2026-10-17。已接入只指完成适配代码；联网测试结果另行记录。字段/配额/价格以实际账号、套餐和模型为准，不把网站展示能力当成API权限。

| 平台 | 对本项目的价值 | 关键限制 | 原型状态 |
|---|---|---|---|
| Open-Meteo | 高、中、低云，湿度、降水、能见度；模型选择；另有历史预报产品 | 各模型变量不同；免费开放接口与商业服务条件不同；Best Match不是独立模型 | 已实现适配、GFS/ICON切换 |
| MET Norway / Yr | Locationforecast完整接口含高、中、低云量，降水、湿度、风 | 全球与区域产品不同；可能共享ECMWF；本适配器没有能见度；须识别User-Agent与遵守流量规则 | 已实现适配 |
| meteoblue | 分层云和多模型云量产品，适合模型分歧与复杂地形研究 | 需注册，核对套餐、区域覆盖与授权；未实测 | 候选，优先评估 |
| Windy | Point Forecast的结构化预报；独立地图产品 | 需密钥；字段取决于模型；测试与正式产品、衍生服务许可需核对 | 候选 |
| Tomorrow.io | 云底、云幕、能见度等辅助变量及数据层 | 字段可用性随权限变化；不能据此假定完整高/中/低云 | 候选 |
| 和风天气 | 逐小时总云量、能见度、降水、国内应用配套 | 此逐小时接口没有足够证据支持高/中/低分层云，不能替代主评分数据源 | 辅助候选 |
| Visual Crossing | Timeline总云量、能见度、历史天气查询 | 历史实况不能当作当时发布的历史预报；不能替代分层云 | 辅助/观测研究候选 |

## 官方资料

- Open-Meteo：https://open-meteo.com/en/docs
- Open-Meteo 使用条件：https://open-meteo.com/en/terms
- Open-Meteo 历史预报：https://open-meteo.com/en/docs/historical-forecast-api
- MET JSON字段：https://docs.api.met.no/doc/ForecastJSON
- MET 数据模型：https://docs.api.met.no/doc/locationforecast/datamodel.html
- MET 条款：https://docs.api.met.no/doc/TermsOfService
- meteoblue 预报API：https://docs.meteoblue.com/en/weather-apis/forecast-api/forecast-data
- meteoblue 免费入口：https://content.meteoblue.com/en/access-options/meteoblue-weather-api/free-weather-api
- Windy：https://api.windy.com/point-forecast/docs
- Tomorrow.io：https://docs.tomorrow.io/reference/weather-data-layers
- 和风天气：https://dev.qweather.com/en/docs/api/weather/weather-hourly-forecast/
- Visual Crossing：https://www.visualcrossing.com/resources/documentation/weather-api/timeline-weather-api/

## 接入顺序建议

1. 以 Open-Meteo 提供的明确模型为主线，完成数据完整性和实际云层预报评估。
2. 用 MET Norway 进行另一路获取验证，保留底层模型相关性说明；并非两个平台一致就能宣称高置信度。
3. 获取 meteoblue 套餐样本，比较分层云与多模型字段，这是下一家最值得实测的候选。
4. 根据地点需求加入和风天气；按预算与字段价值评估 Windy / Tomorrow.io。
5. 以合法可留存的历史预报快照和对应摄影观测校准，分开验证评分排序能力、概率校准和色彩强度。

本次没有购买服务、创建付费账号或填入密钥。
