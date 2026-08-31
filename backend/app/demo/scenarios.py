from app.domain import HumanTurn, ParticipantSeed

flagship_participants = [
    ParticipantSeed(participant_id="architect", display_name="陈屿", role="AI 架构师", declared_position="技术成熟度仍是首要门槛", relevant_experience=[{"text": "负责过企业 Agent 架构落地", "source_ref": "seed:architect:delivery"}]),
    ParticipantSeed(participant_id="product", display_name="周宁", role="产品负责人", declared_position="价值闭环比模型参数更关键", relevant_experience=[{"text": "主导过企业产品试点", "source_ref": "seed:product:pilot"}]),
    ParticipantSeed(participant_id="security", display_name="许安", role="安全负责人", declared_position="可追溯与权限边界决定上线", relevant_experience=[{"text": "负责过 AI 安全评审", "source_ref": "seed:security:review"}]),
    ParticipantSeed(participant_id="buyer", display_name="林青", role="企业采购负责人", declared_position="采购责任链是隐性瓶颈", relevant_experience=[
        {"text": "亲历过两轮 AI 供应商采购与试点", "source_ref": "seed:buyer:procurement"}
    ]),
    ParticipantSeed(participant_id="founder", display_name="顾远", role="创业者", declared_position="先用小闭环证明付费价值", relevant_experience=[{"text": "推动过初创公司企业销售", "source_ref": "seed:founder:sales"}]),
]

SCENARIOS = {
    "flagship": [
        HumanTurn(turn_id=1, participant_id="architect", text="技术上模型精度和延迟仍是上线瓶颈。"),
        HumanTurn(turn_id=2, participant_id="product", text="但企业采购更担心预算、招标和责任归属。"),
        HumanTurn(turn_id=3, participant_id="security", text="我亲历的试点里，安全审查需要可追溯证据。"),
    ],
    "natural": [
        HumanTurn(turn_id=1, participant_id="founder", text="我们先界定什么叫真正进入企业？"),
        HumanTurn(turn_id=2, participant_id="product", text="是付费试点，还是进入正式生产？"),
    ],
    "experience": [
        HumanTurn(turn_id=1, participant_id="buyer", text="我亲历过采购，试点预算和正式预算是两套流程。"),
        HumanTurn(turn_id=2, participant_id="architect", text="这个经验能帮助我们重新定义技术验收。"),
    ],
    "pass": [
        HumanTurn(turn_id=1, participant_id="founder", text="现在这些都还是推测，我们缺少一段真实的采购经验来验证责任链。"),
    ],
}
