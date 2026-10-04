"""Deterministic fictional identities, consistent across UI and delivered files.

Only explicitly registered person names are changed. Rule-bearing English words,
article titles, numeric boundaries and entity IDs retain their meaning. Chinese
name lengths are preserved so the name-length lesson has the same evidence.
"""
import base64
import hashlib
import random
import re

# The fictional source roster is shared by several native app fixtures.
SOURCE_NAMES = '''林若宁 陈以安 许知遥 沈沐言 陈嘉树 许清和 程知夏 苏念 许知远 唐清越
陈子安 许安 欧阳晓 周思远 李可 张宁 王悦 刘晨 赵然 沈一舟 陈明远 顾安 苏晴 李知夏 周小满
陆洲 唐可心 秦朗 宋雨 吴书言 程小禾 何予安 周予安 陆星河 宋清越 季云舟 方明远
方宁 江夏 陶然 顾川 沈悦 韩清 白景川 邓嘉禾 魏星河 余清越 姜予墨 孟书遥 江林
南宫星澜 夏侯沐辰 宇文景宁 公孙若水 皇甫明泽 端木清和 欧阳若宁 司徒景云 司马知夏
上官云舟 诸葛明远 东方予安 欧阳书言 司徒清和 上官知远 东方雨晴 诸葛星河 司马嘉禾'''.split()
# Disjoint family names prevent a tutorial identity leaking into held-out work.
FAMILIES = {
    'demo': [('宋','Song'),('周','Zhou'),('罗','Luo'),('何','He'),('孟','Meng'),('杜','Du'),('邵','Shao'),('梁','Liang'),('冯','Feng'),('顾','Gu'),('汪','Wang'),('任','Ren')],
    'inference': [('郑','Zheng'),('杨','Yang'),('蒋','Jiang'),('邹','Zou'),('卢','Lu'),('姚','Yao'),('廖','Liao'),('潘','Pan'),('贺','He'),('邱','Qiu'),('邓','Deng'),('曾','Zeng')],
}
GIVEN = [('文博','Wenbo'),('思齐','Siqi'),('晓岚','Xiaolan'),('嘉宁','Jianing'),('明哲','Mingzhe'),('雨桐','Yutong'),('安琪','Anqi'),('子恒','Ziheng'),('婉清','Wanqing'),('若彤','Ruotong'),('瑞晨','Ruichen'),('景行','Jingxing'),('可欣','Kexin'),('天佑','Tianyou'),('书涵','Shuhan'),('嘉敏','Jiamin'),('乐然','Leran'),('静宜','Jingyi'),('昕悦','Xinyue'),('浩然','Haoran'),('知新','Zhixin'),('文静','Wenjing'),('逸凡','Yifan'),('心怡','Xinyi')]
SINGLE = '宁珊敏涛慧辰欣澄帆悦静璇航然晴杰洋晨佳涵萱琪轩嘉'
COMPOUND = {'demo':['欧阳','司马','上官','东方'],'inference':['南宫','夏侯','宇文','公孙']}


def roster(task_id, seed, mode=None):
    mode = 'demo' if (mode == 'demo' or mode is None and seed < 1000) else 'inference'
    rng = random.Random(f'identities-v1:{task_id}:{seed}:{mode}')
    return mode, rng


def identity_map(task_id, seed, mode=None):
    mode, rng = roster(task_id, seed, mode)
    pools = {
        2: [family+given for family,_ in FAMILIES[mode] for given in SINGLE],
        3: [family+given for family,_ in FAMILIES[mode] for given,_ in GIVEN],
        4: [family+given for family in COMPOUND[mode] for given,_ in GIVEN],
    }
    for length in pools:
        pools[length] = [n for n in pools[length] if not any(old in n for old in SOURCE_NAMES)]
        rng.shuffle(pools[length])
    return {old:pools[len(old)].pop() for old in SOURCE_NAMES}


# Equivalent business settings, not arbitrary word decoration. Every alias keeps
# the original work purpose and character count, and appears in all references.
SETTING_ALIASES = {
    '春季发布': ['新品发布','版本发布','秋季发布','年度发布','产品发布','服务发布'],
    '客户培训': ['伙伴培训','客户研修','用户培训','客户讲习','代理培训','客户实训'],
    '园区导览': ['展区导览','园区讲解','园区走访','展馆导览','基地导览','园区参访'],
    '产品验收': ['系统验收','交付验收','平台验收','版本验收','项目验收','设备验收'],
    '官网发布': ['网站发布','主页发布','站点发布','门户发布','网站上线','站点上线'],
    '运营交接': ['值班交接','轮班交接','客服交接','夜班交接','班组交接','服务交接'],
    '春日市集': ['周末市集','秋日市集','社区市集','夏夜市集','邻里市集','公益市集'],
    '图书馆夜读': ['社区夜读会','书店夜读会','校园夜读会','街区夜读会','周末夜读会','邻里夜读会'],
    '社区开放日': ['园区开放日','校园开放日','展馆开放日','邻里开放日','工坊开放日','场馆开放日'],
    '周末音乐会': ['午间音乐会','草坪音乐会','社区音乐会','室内音乐会','校园音乐会','露台音乐会'],
    '青禾设计': ['松溪设计','秋棠设计','青桐设计','澄湖设计','松鹤设计','竹溪设计'],
    '星桥': ['明川','云栈','晴岚','江舟','朗月','远辰'],
    '云帆': ['海岳','湖汀','锦航','碧川','临江','远海'],
    '山岚': ['秋岭','远山','松岭','青峰','岚溪','云岭'],
    '白鹭': ['青雁','沙鸥','鸣鹤','青雀','云鹤','海燕'],
    '远川': ['秋江','望江','清渠','长溪','晴川','新河'],
    '海棠路': ['银杏路','梧桐路','玉兰路','槐荫路','桂花路','紫藤路'],
}


def setting_map(task_id,seed,mode=None):
    mode,rng=roster(task_id,seed,mode)
    # Tutorial and execution receive separate plausible settings.
    offset=0 if mode=='demo' else 3
    return {old:aliases[offset+rng.randrange(3)] for old,aliases in SETTING_ALIASES.items()}


def contextualize(state, mode=None):
    """Resolve every textual reference, including downloadable UTF-8 materials.

    Idempotent for a given instance: generated identities are outside the source
    roster. Preserve duplicate people where the task deliberately checks IDs.
    """
    task_id=state['task_id'];seed=state.get('seed',0)
    mapping=identity_map(task_id,seed,mode)
    # Passport spelling must remain consistent with the displayed Chinese name.
    family_py={family:py for families in FAMILIES.values() for family,py in families}
    given_py=dict(GIVEN)
    replacements={**mapping, **setting_map(task_id,seed,mode)}
    travel=[]
    for person in state.get('world',{}).get('people',[]):
        original=person.get('name','').split('（')[0]
        if original in mapping and person.get('surname') and person.get('given_name'):
            new=mapping[original];surname=family_py[new[0]];given=given_py[new[1:]]
            for separator in ('',' '):
                replacements[person['surname']+separator+person['given_name']]=surname+separator+given
            travel.append((person['id'],surname,given))
    pattern=re.compile('|'.join(re.escape(s) for s in sorted(replacements,key=len,reverse=True)))
    def text(value):return pattern.sub(lambda m:replacements[m.group()],value)
    def visit(value):
        if isinstance(value,str):return text(value)
        if isinstance(value,list):return [visit(x) for x in value]
        if not isinstance(value,dict):return value
        result={k:visit(v) for k,v in value.items()}
        if isinstance(value.get('content'),str) and 'sha256' in value and 'size' in value:
            try:
                raw=base64.b64decode(value['content'],validate=True)
                data=text(raw.decode('utf-8')).encode('utf-8')
            except (ValueError,UnicodeError):pass
            else:
                result.update(content=base64.b64encode(data).decode(),size=len(data),sha256=hashlib.sha256(data).hexdigest())
        return result
    result=visit(state)
    for pid,surname,given in travel:
        person=next(p for p in result['world']['people'] if p['id']==pid)
        person.update(surname=surname,given_name=given)
    result.setdefault('source',{}).setdefault('operator',mapping['周予安'])
    return result
