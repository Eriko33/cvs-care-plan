# Care Plan 生成系统 — Design Doc

## 1. 背景 & 目标用户

- **使用者**：CVS 的医疗工作者（药剂师 / Pharmacist）。**病人不直接接触此系统**。
- **使用场景**：医疗工作者为病人开药时，需要生成一份 Care Plan。生成后由医疗工作者**打印**并交给病人。
- **核心价值**：结构化生成 Care Plan，同时在录入环节做患者/订单/处方者的重复与错误检测，避免打乱现有工作流程，并为 pharma 报告提供可靠数据。

## 2. 核心概念

| 概念 | 说明 |
| --- | --- |
| **Order（订单）** | 一次开药记录，对应一种药物 |
| **Care Plan** | 一个订单生成一个 Care Plan（**1 Order : 1 Care Plan : 1 药物**） |
| **Patient（患者）** | 由 Name、DOB、MRN 标识 |
| **Provider（处方者）** | 由 NPI、Provider 姓名标识 |

## 3. 功能需求总览

| 功能 | 优先级 | 说明 |
| --- | --- | --- |
| 患者/订单重复检测 | 必须 | 防止同一患者同一药物被重复提交，同时不能打断正常续方流程 |
| Care Plan 生成 | 必须（核心） | 按标准结构生成，供打印 |
| Provider 重复检测 | 必须 | 保证 NPI 唯一性，影响 pharma 报告准确性 |
| 导出报告 | 必须 | 供 pharma 报告使用 |
| Care Plan 下载 | 必须 | 用户需要将文件上传到他们自己的系统 |

## 4. Care Plan 内容规范

一个 Care Plan（对应一个 Order / 一种药物）必须包含以下四个部分：

1. **Problem List** — 与该药物相关的健康问题 / 用药问题列表
2. **Goals** — 治疗目标
3. **Pharmacist Interventions** — 药剂师采取的干预措施
4. **Monitoring Plan** — 后续监测计划

> 生成后的 Care Plan 需支持**打印**（供交给病人）和**下载**（供上传至医疗工作者自己的系统）。

## 5. 重复检测规则

系统在提交订单 / 录入患者 / 录入处方者信息时，需按以下规则进行校验：

| # | 场景 | 判定条件 | 处理方式 | 原因 |
| --- | --- | --- | --- | --- |
| 1 | 患者重复提交 | 同一患者 + 同一药物 + **同一天** | ❌ **ERROR**，阻止提交 | 判定为重复提交，无需用户确认 |
| 2 | 患者续方 | 同一患者 + 同一药物 + **不同天** | ⚠️ **WARNING**，可确认后继续 | 可能是正常续方 |
| 3 | MRN 冲突 | MRN 相同，但 Name 或 DOB 不同 | ⚠️ **WARNING**，可确认后继续 | 可能是录入错误 |
| 4 | 疑似同一人 | Name + DOB 相同，但 MRN 不同 | ⚠️ **WARNING**，可确认后继续 | 可能是同一患者（如换过 MRN） |
| 5 | Provider（NPI）冲突 | NPI 相同，但 Provider 姓名不同 | ❌ **ERROR**，必须修正后才能提交 | NPI 是唯一标识，不允许歧义，直接影响 pharma 报告的准确性 |

**设计原则**：
- **ERROR**：阻断性错误，无法绕过，必须先修正数据或取消操作。
- **WARNING**：非阻断性提示，医疗工作者确认后可继续，保证正常工作流（如续方）不被打断。

## 6. 关键数据字段（推导自校验规则）

- **Patient**：Name、DOB、MRN
- **Order**：Patient、药物（Drug/Medication）、日期（用于判断"同一天/不同天"）
- **Provider**：NPI、Provider Name

## 7. 导出报告

- 用于生成 **pharma 报告**，需要汇总 Care Plan / Order / Provider 相关数据。
- 需要包含 Provider 重复检测所依赖的字段（NPI、Provider Name），保证报告数据的唯一性和准确性。

## 8. 待确认事项（Open Questions）

- "同一天"的判定是否需要考虑时区 / 门店营业时间边界？
- WARNING 被用户"确认继续"后，是否需要记录确认日志（用于审计 / pharma 报告追溯）？
- 导出报告的具体格式（字段、粒度、导出频率：单次导出 vs 批量/定时导出）尚未明确。
- Care Plan 下载的文件格式（PDF / 其他）尚未明确。
- Problem List / Goals / Pharmacist Interventions / Monitoring Plan 四部分内容是否有模板库（按药物预设），还是完全由药剂师手动录入？
