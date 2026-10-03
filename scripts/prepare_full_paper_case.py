"""Prepare an anonymous synthetic forecasting/inventory/fleet paper case."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BRIEF = '''# 需求预测驱动的低碳配送与库存协同决策

## 数据性质与任务边界
这是原创匿名合成建模题，不是官方竞赛题或实测经营数据。需求以吨/日计，180日完整序列在 demand.csv；day 是1起的连续日号。生成过程为70+0.18t+12sin(2πt/7)+6cos(2πt/7)+正态扰动，标准差4吨，随机种子20261002；按四位小数保存。生成式仅用于说明夹具来源，不作为已知未来需求或预测模型答案。

## 问题一：数据与预测
按日期审计数据、描述趋势/周期/波动；固定1–120日训练，121–150日验证，151–180日测试。比较训练均值、最后一周重复、线性趋势、线性趋势+周周期四种预测。季节朴素在30日预测期循环使用训练末7日，不用验证/测试观测更新。OLS 周期特征为[1,t,sin(2πt/7),cos(2πt/7)]。用验证RMSE选择模型；并列按模型复杂度从均值到周期趋势排序。选择后仅在1–150日重估，预测测试期和181–210日。报告RMSE、MAE、平均偏差；误差定义预测减实际。不要在测试集选模型，不将相邻时点误差当独立样本构造未经检验的显著性结论。

## 问题二：每日车队整数决策
车型A单日载量22吨、固定出车成本1100元、排放45kg CO2；车型B为35吨、1800元、65kg CO2。每天A最多6辆、B最多4辆，每辆最多执行一趟。出车成本按实际选择车数计算，货量可以低于总载量。给定订货量q≥0，最小化1100a+1800b+碳价(45a+65b)，且22a+35b≥q、a∈{0,…,6}、b∈{0,…,4}。若不可行明确记录；最优值并列时保留全部最优方案，实际执行取剩余载量最小、随后a最小的方案。基准碳价0.2元/kg CO2；q=0用零车辆。

## 问题三：库存政策选择
候选安全库存s∈{0,5,10,15,20,25,30}吨。每个独立模拟期开始有免费给定库存I0=s；这是假设，不把它称采购成本已完整计算。第t日订货q_t=max(0,预测需求_t+s-I_(t-1))，当天到货。实际服务u_t=min(y_t,I_(t-1)+q_t)，缺货l_t=y_t-u_t，期末库存I_t=I_(t-1)+q_t-u_t。持有成本10元/(吨·日)，缺货损失600元/吨。总成本=车队成本+碳成本+期末库存持有成本+缺货损失；无采购成本、固定仓储投资和残值。履约率=Σu/Σy，不能称为无缺货日比例。在验证期用问题一的训练期预测分别选择名义最小总成本库存（并列取小s）；测试只评估冻结的政策。

## 问题四：不确定需求与稳健选择
将验证需求按倍率{0.85,0.925,1,1.075,1.15}缩放，预测不随倍率提前变化。每个情景从I0=s开始，先分别计算所有库存候选的成本；遗憾=该政策成本减此情景内最优成本。最小化最大遗憾选择稳健库存（并列取小s）。冻结这一选择，在相同倍率的测试情景上报告成本、排放、履约率与最大遗憾；测试情景的最优值仅用于评价，不能反向重选政策。不要把有限情景保障外推成任意分布的保障。

## 问题五：参数敏感性与适用性
碳价{0,0.2,0.5}与缺货损失{300,600,900}构成9组参数，在验证期重新选择名义/稳健政策，再独立测试。分析政策切换、成本分解、排放与服务权衡；另外讨论免费初库存、即时到货、无路线距离与已知运力上限的影响，不能把本题称为已经解决路径规划。

## 交付
论文摘要、正文、AI声明及文献合计至少21页，不包含代码附录。用必要推导、结果和检验扩写，正文不放制作清单、字数指标、检查器状态或内部路径。提供完整数据、可运行求解程序、未舍入结果JSON、全部逐日CSV、数据图和机制图源、可编辑论文及支撑包。文献来源由宿主核验并提供，不能编造。
'''

def prepare(output: Path) -> dict:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    rng = np.random.default_rng(20261002)
    day = np.arange(1,181)
    demand = np.maximum(0,70 + .18*day + 12*np.sin(2*np.pi*day/7)
                        + 6*np.cos(2*np.pi*day/7) + rng.normal(0,4,len(day)))
    with (output/'demand.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.writer(f); writer.writerow(['day','demand_tonnes'])
        writer.writerows((int(t),f'{y:.4f}') for t,y in zip(day,demand))
    (output/'brief.md').write_text(BRIEF,encoding='utf-8')
    cfg={'schema_version':1,'data_kind':'synthetic','seed':20261002,
         'training_end':120,'validation_end':150,'test_end':180,'forecast_end':210,
         'safety_stocks':[0,5,10,15,20,25,30],
         'demand_scales':[.85,.925,1,1.075,1.15],
         'fleet':{'A':{'capacity':22,'cost':1100,'emission':45,'max':6},
                  'B':{'capacity':35,'cost':1800,'emission':65,'max':4}},
         'carbon_prices':[0,.2,.5],'shortage_costs':[300,600,900],
         'holding_cost':10,'base_carbon_price':.2,'base_shortage_cost':600,
         'paper_pages':{'minimum':21,'includes':['summary','body','ai_statement','references'],'excludes':['code_appendix']}}
    (output/'case.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    context_files=['SKILL.md','references/evidence-and-writing.md','references/longform-paper.md',
                   'references/scientific-mechanisms.md','references/paper-voice.md',
                   'vendor/MathModelAgent/skills/2analysis-modeling/SKILL.md']
    context='\n\n'.join('## '+p+'\n'+(ROOT/p).read_text(encoding='utf-8') for p in context_files)
    (output/'skill-context.md').write_text(context,encoding='utf-8')
    data=(output/'demand.csv').read_text(encoding='utf-8')
    prompt=context+'\n\n'+BRIEF+'\n\nDATA CSV:\n'+data+'''

本次你只负责生成模型与程序，不具备执行工具。返回一个完整JSON对象（可用json外层代码围栏），不要假称已运行。字段：
{"title":"论文题目","model_notes":"中文推导与算法说明，约1500–2200字","python_source":"完整UTF-8 Python程序","diagram_claim":"机制图一句主张"}。
程序仅用Python标准库和NumPy，不联网、不读凭据、不启动子进程、不动态执行，不调用图形库。CLI参数为 --data-dir 和 --output，读data-dir里的demand.csv和case.json，把结果写到新output目录。允许pathlib、argparse、csv、json、math、numpy；输出未舍入的results.json、daily-validation.csv、daily-test.csv、forecast.csv、policy-grid.csv、scenario-grid.csv、sensitivity.csv。
results.json必须含 forecasts: {selected_model, validation_metrics: 每模型 {rmse,mae,bias}, test_metrics: {rmse,mae,bias}, coefficients:所选模型重估系数数组}; policies:{nominal_stock,robust_stock}; baseline:{nominal,robust:各有 total_cost, fleet_cost, carbon_cost, holding_cost, shortage_cost, emissions, fill_rate, shortage_tonnes, mean_stock}; scenarios:数组，每项scale,stock,total_cost,emissions,fill_rate,regret；sensitivity:数组，每项carbon_price,shortage_price,nominal_stock,robust_stock,test_nominal_cost,test_robust_cost。
daily-test.csv为所选名义政策，列day,actual,predicted,order,served,shortage,inventory,a,b,fleet_cost,carbon_cost,holding_cost,shortage_cost,emissions；daily-validation.csv同结构。forecast.csv列day,predicted；policy-grid.csv列stock,total_cost,fill_rate,emissions；scenario-grid.csv列scale,stock,total_cost,fill_rate,emissions,regret；sensitivity.csv与JSON同字段。所有情景网格均为测试期，用已冻结的预测；选择政策只用验证期。
仔细处理季节朴素的起点、测试重估、逐日库存信息时序、遗憾计算与零车方案。不要返回预先填好的数值，不把合成需求包装成实测。程序要在同样输入下可复现。
'''
    (output/'solver-prompt.txt').write_bytes(prompt.encode('utf-8'))
    manifest={'case':'forecast-inventory-fleet-v1','data_kind':'synthetic','context_files':context_files,
              'hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}}
    (output/'input-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return manifest

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();print(json.dumps(prepare(args.output),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
