import re
sm_fmt = r'[bpmfdtnlgkhjqxrzcsyw]'
nosm_fmt = r'eR|aNG?|eNG?|iNG?|uN|vN|oNG'
rep_fmt = r'([ZCS])(H)'
nosmym_fmt = r'(er|ang?|eng?|ing?|un|vn|ong)([aoeiuv])'

def _abbr_chinese_name(name:str):
    polysyls = re.split('\'|-', name)
    monosyls = []
    for polysyl in polysyls:
        sep_syl = _split_chinese_syl(polysyl)
        monosyls.extend(sep_syl)
    abbr = ''.join(_[0].upper()+'. ' for _ in monosyls)
    abbr = abbr.rstrip(' ')
    return abbr

def _split_chinese_syl(polysyl:str):
    polysyl = polysyl.lower()
    polysyl = re.sub(sm_fmt, lambda match:match.group(0).upper(), polysyl)
    polysyl = re.sub(nosm_fmt, lambda match:match.group(0).lower(), polysyl)
    polysyl = re.sub(rep_fmt, lambda match:match.group(1).upper()+match.group(2).lower(), polysyl)
    polysyl = re.sub(nosmym_fmt, lambda match:match.group(1)[:-1]+match.group(1)[-1].upper()+match.group(2).lower(), polysyl)

    sep_syl = []
    idx_f = 0
    for idx_s, s in enumerate(polysyl):
        if ('A'<=s<='Z') and (idx_s!=0):
            sep_syl.append(polysyl[idx_f:idx_s])
            idx_f = idx_s
    sep_syl.append(polysyl[idx_f:])
    sep_syl = [_.capitalize() for _ in sep_syl]
    return sep_syl

def _abbr_nonchinese_name(name:str):
    return ''.join(_[0].upper() for _ in re.split('\s|-', name))