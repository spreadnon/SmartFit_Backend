import json
import os
import re

def translate_name(name):
    # Mapping for fitness terminology
    mapping = {
        # High Priority Full Phrases
        "Hammer Grip Incline DB Bench Press": "对握斜板哑铃卧推",
        "Skull Crusher": "碎颅式/仰卧臂屈伸",
        "Skullcrusher": "碎颅式/仰卧臂屈伸",
        "Pull Apart": "拉开/拉伸",
        "Good Morning": "早安式",
        "Farmer's Walk": "农夫行走",
        "Russian Twist": "俄罗斯转体",
        "Mountain Climber": "登山者",
        "Flutter Kick": "交替踢腿",
        "Scissor Kick": "剪刀腿",
        "Around the World": "环绕世界",
        "Around The World": "环绕世界",
        "Atlas Stone": "大力士石球",
        "Balance Board": "平衡板",
        "Battling Rope": "战绳",
        "Body Up": "身体撑起",
        "Bottoms Up": "底部向上",
        "Butt Up": "臀部抬起",
        "Child's Pose": "婴儿式",
        "Circus Bell": "马戏团哑铃",
        "Conans Wheel": "柯南转轮",
        "Dead Bug": "死虫式",
        "London Bridge": "伦敦桥",
        "Monster Walk": "怪兽步",
        "Otis Up": "奥蒂斯起身",
        "Recumbent Bike": "靠背单车",
        "Side Bridge": "侧撑",
        "Side Jackknife": "侧卧折体",
        "Glute Kickback": "臀部后踢",
        "Anti Gravity": "抗重力",
        "Anti-Gravity": "抗重力",
        "Pull Through": "髋部伸展",
        "Pull-Through": "髋部伸展",
        "Long Bar": "长杆",
        "Bear Crawl": "熊爬",
        "Bosu Ball": "波速球",
        "Medicine Ball": "药球",
        "Exercise Ball": "健身球",
        "Stability Ball": "稳定性球",
        "Swiss Ball": "瑞士球",
        "Floor Press": "地板推举",
        "Hammer Curl": "锤式弯举",
        "Zottman Curl": "佐特曼弯举",
        "Concentration Curl": "集中弯举",
        "Preacher Curl": "布道师弯举/斜托弯举",
        "Spider Curl": "蜘蛛弯举",
        "Wrist Curl": "腕弯举",
        "Military Press": "军式推举",
        "Push Press": "总推",
        "Arnold Press": "阿诺德推举",
        "Step Up": "登阶",
        "Step-Up": "登阶",
        "Face Pull": "面拉",
        "All Fours": "四足位",
        "All Four": "四足位",
        "Leg Press": "腿举",
        "Leg Extension": "腿屈伸",
        "Leg Curl": "腿弯举",
        "Ab Rollout": "腹肌轮滚出",
        "Calf Raise": "提踵",
        "Lateral Raise": "侧平举",
        "Front Raise": "前平举",
        "Upright Row": "直立划船",
        "Bent Over": "俯身",
        "Bent-Over": "俯身",
        "Shoulder Press": "肩推",
        "Clean and Jerk": "挺举",
        "Power Clean": "高翻",
        "Hang Clean": "悬垂翻",
        "Bicycling": "骑行",
        "Stationary": "固定",
        "Internal Rotation": "内旋",
        "External Rotation": "外旋",
        "Iron Cross": "铁十字",
        "Judo Flip": "柔道翻",
        "Lat Pulldown": "高位下拉",
        "Pulldown": "下拉",
        "Pushdown": "下压",
        
        # Actions / Movements
        "Bench Press": "卧推",
        "Pullover": "仰卧拉举",
        "Shrug": "耸肩",
        "Throw": "投掷",
        "Clean": "翻站",
        "Snatch": "抓举",
        "Press": "推举",
        "Squat": "深蹲",
        "Deadlift": "硬拉",
        "Row": "划船",
        "Curl": "弯举",
        "Extension": "臂屈伸",
        "Raise": "平举/提升",
        "Flyes": "飞鸟",
        "Fly": "飞鸟",
        "Lunge": "箭步蹲",
        "Crunch": "卷腹",
        "Sit-Up": "仰卧起坐",
        "Dip": "撑体/臂屈伸",
        "Pull-Up": "引体向上",
        "Pullup": "引体向上",
        "Chin-Up": "引体向上",
        "Push-Up": "俯卧撑",
        "Pushup": "俯卧撑",
        "Burpee": "波比跳",
        "Jump": "跳跃",
        "Stretch": "拉伸",
        "Plank": "平板支撑",
        "Twist": "转体",
        "Thrust": "顶髋/推举",
        "Bridge": "桥式",
        "Abduction": "外展",
        "Adduction": "内收",
        "Rotation": "旋转",
        "Rollout": "滚出",
        "Sprint": "冲刺",
        "Climb": "攀爬",
        "SMR": "筋膜放松",
        "Windmill": "风车",
        "Circle": "环绕",
        "Toucher": "触摸",
        "Bound": "跳跃",
        "Drag": "拖拽",
        "Thru": "穿过",
        "Walk": "行走",
        "Walking": "步行",
        "Bend": "侧屈/弯曲",
        "Crawl": "爬行",
        "Kick": "踢腿",
        "Leap": "跳跃",
        "Lift": "抬起",
        "Skip": "跳跃/垫步",
        "Tuck": "收腹",
        "Pike": "折体",
        "Swing": "摆动",
        "Butterfly": "蝴蝶式",
        "Crossover": "交叉",
        "Flip": "翻转",
        "Jerk": "挺举",
        "Pull": "拉",
        "Block": "架子",
        "Release": "释放",
        "Run": "跑",
        
        # Modifiers / Positions
        "Straight-Arm": "直臂",
        "Straight Arm": "直臂",
        "Incline": "上斜",
        "Decline": "下斜",
        "Seated": "坐姿",
        "Standing": "站姿",
        "Lying": "仰卧",
        "Bent Arm": "屈臂",
        "Bent": "弯曲",
        "Kneeling": "跪姿",
        "One-Arm": "单臂",
        "One Arm": "单臂",
        "Single-Arm": "单臂",
        "Two-Arm": "双臂",
        "One-Leg": "单腿",
        "One Leg": "单腿",
        "Single-Leg": "单腿",
        "Two-Dumbbell": "双哑铃",
        "Alternating": "交替",
        "Alternate": "交替",
        "Reverse": "反向",
        "Neutral Grip": "对握",
        "Hammer Grip": "对握/锤式",
        "Close-Grip": "窄握",
        "Close Grip": "窄握",
        "Wide-Grip": "宽握",
        "Wide Grip": "宽握",
        "Medium Grip": "中等握距",
        "Pronated": "正手",
        "Supinated": "反手",
        "Rear": "后侧",
        "Front": "前侧",
        "Side": "侧向",
        "Lateral": "侧向",
        "Diagonal": "对角线",
        "Advanced": "高级",
        "Beginner": "初级",
        "Intermediate": "中级",
        "Expert": "专家",
        "Low-Pulley": "低位绳索",
        "High-Pulley": "高位绳索",
        "Behind The Neck": "颈后",
        "Overhead": "过顶/颈后",
        "Split": "分腿",
        "T-Bar": "T型杆",
        "Smith": "史密斯",
        "Landmine": "地雷管",
        "Jefferson": "杰斐逊",
        "Hack": "哈克",
        "Sissy": "西斯",
        "Box": "箱式",
        "Sumo": "相扑",
        "Romanian": "罗马尼亚",
        "Stiff-Legged": "直腿",
        "Stiff Legged": "直腿",
        "Full": "全",
        "Partials": "半程",
        "Assisted": "辅助",
        "Guillotine": "断头台式",
        "Renegade": "叛逆者",
        "Arnold": "阿诺德",
        "Backward": "向后",
        "Behind": "在...后",
        "Against": "依靠",
        "Towards": "朝向",
        "Underhand": "反手/反握",
        "Overhand": "正手/正握",
        "Multiple": "多个",
        "Response": "响应/动作",
        "Position": "姿势/位置",
        "Mid": "中",
        "Two": "双",
        "Ups": "起/登",
        "Up": "起",
        "Hang": "悬垂",
        "Internal": "内侧",
        "External": "外侧",
        "Extended": "伸展",
        "Around": "环绕",
        "World": "世界",
        "Upper": "上肢",
        "Point": "点",
        "Single": "单",
        
        # Equipment
        "Barbell": "杠铃",
        "Dumbbell": "哑铃",
        "Kettlebell": "壶铃",
        "Cable": "绳索",
        "Machine": "器械",
        "EZ-Bar": "EZ杆",
        "EZ Bar": "EZ杆",
        "Band": "弹力带",
        "Bodyweight": "自重",
        "Body Only": "自重",
        "Plate": "杠铃片",
        "Foam Roll": "泡沫轴",
        "Roller": "滚轮",
        "Sled": "雪橇",
        "Prowler": "雪橇",
        "Ring": "吊环",
        "Rope": "绳索",
        "Chain": "铁链",
        "Bench": "长凳",
        "Box": "箱子",
        "Step": "踏板",
        "Chair": "椅子",
        "Axle": "粗杠",
        "Wheel": "轮",
        "Stone": "石球",
        "Rack": "架子",
        "Trainer": "训练器",
        "Ball": "球",
        "Bar": "杠",
        "Body": "身体",
        "Palm": "手掌",
        "Head": "头部",
        "Wall": "墙",
        "Hand": "手",
        "Handle": "把手",
        "Attachment": "配件",
        "Board": "板",
        "Chin": "下巴",
        
        # Body Parts
        "Abdominal": "腹部",
        "Abs": "腹部",
        "Ab": "腹肌",
        "Chest": "胸部",
        "Pectoral": "胸部",
        "Shoulder": "肩部",
        "Deltoid": "三角肌",
        "Delt": "三角肌",
        "Biceps": "肱二头肌",
        "Triceps": "肱三头肌",
        "Tricep": "肱三头肌",
        "Back": "背部",
        "Lats": "背阔肌",
        "Traps": "斜方肌",
        "Rhomboids": "菱形肌",
        "Lower Back": "下背部",
        "Middle Back": "中背部",
        "Glute": "臀部",
        "Hamstring": "腘绳肌",
        "Quadriceps": "股四头肌",
        "Quad": "股四头肌",
        "Calf": "小腿",
        "Calves": "小腿",
        "Adductor": "内收肌",
        "Abductor": "外展肌",
        "Groin": "腹股沟",
        "Forearm": "前臂",
        "Wrist": "手腕",
        "Ankle": "脚踝",
        "Foot": "脚部",
        "Leg": "腿部",
        "Hip": "髋部",
        "Knee": "膝盖",
        "Elbow": "肘部",
        "Neck": "颈部",
        "Face": "面部",
        "Heel": "脚后跟",
        "Finger": "手指",
        "Tibialis": "胫骨",
        "Peroneals": "腓骨肌",
        "Piriformis": "梨状肌",
        "Brachialis": "肱肌",
        "Anterior": "前侧",
        "Posterior": "后侧",
        "Torso": "躯干",
        "Core": "核心",
        "Arm": "手臂",
        
        # Others
        "Powerlifting": "力量举",
        "Olympic": "奥林匹克",
        "Driver": "方向盘式",
        "Bradford": "布拉德福德",
        "Rocky": "洛奇",
        "Carioca": "卡里奥卡",
        "Clock": "时钟",
    }
    
    # Specific full names
    full_name_mapping = {
        "3/4 Sit-Up": "3/4仰卧起坐",
        "90/90 Hamstring": "90/90腘绳肌拉伸",
        "Air Bike": "空中单车",
        "Burpee": "波比跳",
        "Plank": "平板支撑",
    }
    
    if name in full_name_mapping:
        return full_name_mapping[name]
        
    name_cn = name
    
    # Pre-processing: remove common prepositions and connectors if they are separate words
    to_remove = ["The", "An", "A", "And", "With", "For", "To", "At", "On", "From", "By", "Of", "In"]
    for word in to_remove:
        name_cn = re.sub(r'\b' + word + r'\b', '', name_cn, flags=re.IGNORECASE)
    
    # Pre-processing: handle plurals (singularize common terms)
    words = name_cn.split()
    processed_words = []
    # Words that should NOT be singularized by removing 's'
    exclude_from_singular = ["abs", "lats", "traps", "flyes", "press", "atlas", "swiss", "glutes", "triceps", "biceps", "glass", "stiffness", "ups"]
    
    for word in words:
        lower_word = word.lower()
        if lower_word in exclude_from_singular:
            processed_words.append(word)
        elif lower_word.endswith('s') and len(word) > 3:
            processed_words.append(word[:-1])
        else:
            processed_words.append(word)
    name_cn = " ".join(processed_words)
    
    # Translation
    sorted_keys = sorted(mapping.keys(), key=len, reverse=True)
    
    for en in sorted_keys:
        # Use word boundaries
        pattern = re.compile(r'\b' + re.escape(en) + r'\b', re.IGNORECASE)
        name_cn = pattern.sub(mapping[en], name_cn)
            
    # Post-processing: clean up
    name_cn = name_cn.replace("-", " ").strip()
    name_cn = " ".join(name_cn.split())
    
    return name_cn

def main():
    file_path = "/Users/jeremychen/Desktop/smart_fitness/free-exercise-db-main/dist/exercises.json"
    
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return

    print(f"Reading {file_path}...")
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"Processing {len(data)} exercises...")
    for exercise in data:
        en_name = exercise.get("name", "")
        exercise["nameCN"] = translate_name(en_name)
    
    print(f"Writing updated data back to {file_path}...")
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print("Done!")

if __name__ == "__main__":
    main()
