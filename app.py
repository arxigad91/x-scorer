import streamlit as st
import re
import random

# --- 設定: 仮想的なアルゴリズムの重み (公開情報を元にした近似値) ---
WEIGHTS = {
    "like": 0.5,
    "retweet": 1.0,
    "reply": 13.5,  # 対話は非常に重い
    "image": 2.0,   # メディアがある場合の係数（ブースト）
    "video": 2.0,
    "link": -1.0,   # リンク付きは減点傾向（リプライ誘導推奨）
}

st.set_page_config(page_title="X Algo Pipeline Sim", layout="wide")

# --- クラス定義: パイプラインの各ステージ ---

class PostCandidate:
    def __init__(self, text, has_media, is_premium, follower_count):
        self.text = text
        self.has_media = has_media
        self.is_premium = is_premium
        self.follower_count = follower_count
        self.flags = []
        self.score_breakdown = {}
        self.final_score = 0

def stage_1_candidate_sources(post):
    """
    STAGE 1: CANDIDATE SOURCES
    In-Network (Thunder) と Out-of-Network (Phoenix) の候補になるか判定
    """
    log = []
    status = "PASS"
    
    # Out-of-Network (おすすめ) に載るための最低条件シミュレーション
    # フォロワー比率や直近の活動などが影響するが、ここでは簡易的に判定
    
    source_type = "In-Network Only (Thunder)"
    if post.is_premium or post.follower_count > 500:
        source_type = "Global Candidate (Phoenix Retrieval)"
        log.append("✅ **Phoenix Retrieval**: おすすめ（FF外）表示の候補として抽出されました。")
    else:
        log.append("ℹ️ **Thunder Only**: フォロワー数が少ない、または活動が浅いため、主にフォロワー内（In-Network）での表示候補となります。")
    
    return status, log, source_type

def stage_2_filtering_pre_scoring(post):
    """
    STAGE 2: FILTERING (Pre-Selection)
    重複、ブロック、ミュートワード、スパムなどの排除
    """
    log = []
    status = "PASS"
    
    # 1. スパム/ミュートワード判定（簡易）
    spam_keywords = ["稼げる", "無料配布", "giveaway", "dm me"]
    if any(word in post.text.lower() for word in spam_keywords):
        status = "DROP"
        log.append(f"⛔ **Muted Keyword**: スパム系の単語が含まれているため、フィルタリングされました。")
        return status, log

    # 2. ハッシュタグ過多（スパム判定）
    hashtags = re.findall(r'#\w+', post.text)
    if len(hashtags) > 5:
        status = "DROP"
        log.append(f"⛔ **Spam Filter**: ハッシュタグが多すぎます（{len(hashtags)}個）。スパム判定されるリスクがあります。")
        return status, log

    # 3. テキストの長さ（短すぎるとボット判定リスク）
    if len(post.text) < 5 and not post.has_media:
        status = "WARNING"
        log.append("⚠️ **Low Quality**: テキストが短すぎます。メディアがない場合、ノイズとして除去される可能性があります。")

    if status == "PASS":
        log.append("✅ **Filtering Passed**: 重大なスパム要素は見つかりませんでした。")
        
    return status, log

def stage_3_scoring(post):
    """
    STAGE 3: SCORING (Heavy Ranker / Phoenix Scorer)
    P(like), P(reply) などを予測し、スコア付けを行う工程のシミュレーション
    """
    log = []
    
    # ベーススコア（投稿自体の品質推定）
    base_score = 1.0
    
    # --- Feature Engineering (特徴量抽出) ---
    
    # メディアブースト
    if post.has_media:
        base_score *= WEIGHTS["image"]
        log.append(f"📈 **Media Boost**: 画像/動画あり (x{WEIGHTS['image']})")
    
    # リンクペナルティ
    urls = re.findall(r'http[s]?://', post.text)
    if urls:
        # 実際はリプライ欄ならOKだが、本文リンクは減点
        log.append(f"📉 **Link Penalty**: 外部リンクが含まれています。インプレッションが制限される可能性があります。")
        base_score *= 0.5 
    
    # 対話誘発性 (Question Mark)
    if "?" in post.text or "？" in post.text:
        log.append(f"📈 **Conversation Starter**: 疑問形が含まれており、リプライ率(P_reply)予測が向上します。")
        base_score *= 1.2

    # 長文ブースト (Premiumのみ)
    if len(post.text) > 140 and post.is_premium:
        log.append(f"📈 **Longform Boost**: 長文投稿による滞在時間増加が見込まれます。")
        base_score *= 1.1

    post.base_potential = base_score
    
    # --- Engagement Simulation (予測スコア計算) ---
    # ユーザーに「どれくらい反応が来そうか」を入力させ、アルゴリズム上のスコアを試算
    return base_score, log

def stage_4_filtering_visibility(post, final_score):
    """
    STAGE 4: FILTERING (Post-Selection) & VISIBILITY
    最終的な表示フィルタリング（NSFW、Violenceなど）
    """
    status = "SHOW"
    log = []
    
    # ここで本来は「Visibility Filtering (deleted/spam/violence/gore)」が入る
    # 以前のCLIP判定でNSFWだった場合はここでDROPされる
    
    if final_score < 10:
        status = "LIMITED"
        log.append("⚠️ **Low Score**: スコアが低いため、表示頻度が調整（間引き）される可能性があります。")
    else:
        log.append("✅ **High Visibility**: 十分なスコアがあります。おすすめ表示の有力候補です。")
        
    return status, log

# --- UI構築 ---

st.title("🧬 X Algorithm Pipeline Simulator")
st.markdown("Githubで公開された`x-algorithm`のフロー（Home Mixer）をベースに、投稿がどのように処理・評価されるかをシミュレートします。")

# --- 画面左：投稿作成とシミュレーション設定 ---
with st.sidebar:
    st.header("1. 投稿データ入力")
    input_text = st.text_area("投稿テキスト", placeholder="ここに投稿内容を入力...")
    input_has_media = st.checkbox("画像・動画あり", value=True)
    
    st.header("2. アカウント状態")
    input_premium = st.checkbox("X Premium (青バッジ)", value=False)
    input_followers = st.number_input("フォロワー数", value=500, step=100)
    
    st.markdown("---")
    st.header("3. 反応シミュレーション")
    st.caption("この投稿にどれくらい反応が来ると予想しますか？")
    sim_likes = st.number_input("予想いいね数", value=10)
    sim_replies = st.number_input("予想リプライ数", value=0)
    sim_reposts = st.number_input("予想リポスト数", value=0)
    
    run_btn = st.button("アルゴリズムを実行 (Process Feed)", type="primary")

# --- 画面右：パイプライン可視化 ---

if run_btn and input_text:
    post = PostCandidate(input_text, input_has_media, input_premium, input_followers)
    
    # --- STEP 1: Candidate Sources ---
    st.subheader("📍 Step 1: Candidate Sources (候補選出)")
    s1_status, s1_log, s1_type = stage_1_candidate_sources(post)
    
    col1, col2 = st.columns([1, 3])
    with col1:
        if "Phoenix" in s1_type:
            st.success("GLOBAL CANDIDATE")
        else:
            st.info("LOCAL CANDIDATE")
    with col2:
        st.write(f"**判定**: {s1_type}")
        for l in s1_log: st.write(l)
    
    st.markdown("⬇︎")

    # --- STEP 2: Pre-Scoring Filtering ---
    st.subheader("📍 Step 2: Hydration & Filtering (足切り)")
    s2_status, s2_log = stage_2_filtering_pre_scoring(post)
    
    col1, col2 = st.columns([1, 3])
    with col1:
        if s2_status == "DROP":
            st.error("DROPPED")
        elif s2_status == "WARNING":
            st.warning("WARNING")
        else:
            st.success("PASSED")
    with col2:
        for l in s2_log: st.write(l)
        
    if s2_status == "DROP":
        st.error("🚫 この投稿はフィルタリング段階で破棄されました。修正してください。")
    else:
        st.markdown("⬇︎")
        
        # --- STEP 3: Scoring ---
        st.subheader("📍 Step 3: Scoring (Heavy Ranker予測)")
        base_potential, s3_log = stage_3_scoring(post)
        
        # スコア計算 (Linear Estimation)
        # アルゴリズム内部の重み付き和
        score_val = (sim_likes * WEIGHTS["like"]) + \
                    (sim_replies * WEIGHTS["reply"]) + \
                    (sim_reposts * WEIGHTS["retweet"])
        
        # コンテンツ自体のポテンシャル係数を掛ける
        final_score = score_val * base_potential
        
        col1, col2 = st.columns([1, 3])
        with col1:
            st.metric("Total Score", f"{final_score:.1f}")
        with col2:
            st.markdown("#### Feature Analysis")
            for l in s3_log: st.write(l)
            st.markdown("#### Score Breakdown")
            st.caption(f"Base Potential: x{base_potential:.2f}")
            st.write(f"Like Score: {sim_likes * WEIGHTS['like']:.1f}")
            st.write(f"Reply Score: {sim_replies * WEIGHTS['reply']:.1f} (最重要)")
            st.write(f"Repost Score: {sim_reposts * WEIGHTS['retweet']:.1f}")

        st.markdown("⬇︎")

        # --- STEP 4: Selection & Visibility ---
        st.subheader("📍 Step 4: Selection & Visibility")
        s4_status, s4_log = stage_4_filtering_visibility(post, final_score)
        
        for l in s4_log: st.write(l)
        
        if final_score > 100:
            st.balloons()
            st.success("🎉 **Ranked High**: おすすめフィードの上位に表示される可能性が高いです！")
        elif final_score > 30:
            st.success("✅ **Ranked Mid**: フォロワーのTLには確実に届きます。")
        else:
            st.info("ℹ️ **Ranked Low**: 表示優先度は低めです。リプライ等での加点が必要です。")

elif run_btn:
    st.error("テキストを入力してください。")
