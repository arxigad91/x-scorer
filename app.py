import streamlit as st
import torch
from transformers import CLIPProcessor, CLIPModel
from PIL import Image
import re

# --- 1. 設定 & モデルロード ---
st.set_page_config(page_title="X Post Analyzer", layout="wide")

@st.cache_resource
def load_model():
    # OpenAIのCLIPモデル（軽量版）をロード
    model_name = "openai/clip-vit-base-patch32"
    model = CLIPModel.from_pretrained(model_name)
    processor = CLIPProcessor.from_pretrained(model_name)
    return model, processor

model, processor = load_model()

# --- 2. アルゴリズム判定ロジック ---

def analyze_text(text):
    score_mod = 0
    feedback = []
    
    # URLチェック (アルゴリズム上、本文のURLはインプレッションを下げる要因)
    urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)
    if urls:
        score_mod -= 30
        feedback.append("⚠️ **URLが含まれています**: 外部リンクはリプライ欄に貼ることを強く推奨します（インプレッション低下リスク大）。")
    
    # ハッシュタグチェック
    hashtags = re.findall(r'#\w+', text)
    if len(hashtags) > 5:
        score_mod -= 10
        feedback.append("⚠️ **ハッシュタグ過多**: 5個以上はスパム判定されるリスクがあります。")
    elif len(hashtags) == 0:
        score_mod -= 5
        feedback.append("ℹ️ ハッシュタグがありません。関連タグを1-2個つけると検索流入が増えます。")
    
    # 疑問形チェック (対話を促すため加点)
    if "?" in text or "？" in text:
        score_mod += 10
        feedback.append("✅ **対話促進**: 疑問形が含まれており、リプライを誘発しやすくなっています。")

    # 長文チェック (極端に短いとスルーされやすい)
    if len(text) < 10 and not urls: # URLのみ投稿は別で判定済み
        score_mod -= 10
        feedback.append("⚠️ **テキスト不足**: 文章が短すぎます。文脈（ストーリー）を追加してください。")
        
    return score_mod, feedback, len(urls) > 0

def analyze_image_with_clip(image, target_keywords):
    # CLIPで画像を解析
    
    # 1. NSFW / Safety Check
    # 疑似的にCLIPで「安全」か「疑わしい」かをゼロショット分類
    safety_prompts = ["safe content", "nsfw content", "explicit content", "gore"]
    
    # 2. Cluster Target Check (SimClusters)
    # ユーザーが狙っているジャンル（例: anime, car）として認識されるか
    sim_prompts = [p.strip() for p in target_keywords.split(",")] if target_keywords else ["general image"]
    
    all_prompts = safety_prompts + sim_prompts
    
    inputs = processor(text=all_prompts, images=image, return_tensors="pt", padding=True)
    
    with torch.no_grad():
        outputs = model(**inputs)
    
    # 確率計算
    logits_per_image = outputs.logits_per_image
    probs = logits_per_image.softmax(dim=1).cpu().numpy()[0]
    
    results = dict(zip(all_prompts, probs))
    
    # 判定
    is_unsafe = (results["nsfw content"] + results["explicit content"] + results.get("gore", 0)) > results["safe content"]
    
    return results, is_unsafe

# --- 3. UI構築 ---

st.title("🚀 X (Twitter) Algorithm Post Scorer")
st.markdown("Githubで公開されたアルゴリズムの特性（メディア優遇、URL冷遇、SimClustersなど）を元に、投稿の「伸びやすさ」を診断します。")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📝 投稿内容作成")
    post_text = st.text_area("本文を入力", height=150, placeholder="ここに投稿予定の文章を入力...")
    uploaded_file = st.file_uploader("画像をアップロード (推奨)", type=["png", "jpg", "jpeg", "webp"])
    
    st.markdown("---")
    st.subheader("🎯 ターゲット設定 (SimClusters)")
    st.markdown("AIにどのように認識されたいですか？（カンマ区切りで入力）")
    # ユーザー様の興味に合わせてデフォルト値を設定
    target_tags = st.text_input("ターゲットキーワード", value="anime girl, high quality, illustration, sports car")

with col2:
    st.subheader("📊 診断結果")
    
    if st.button("アルゴリズム診断を実行", type="primary"):
        base_score = 50 # 基準点
        text_mod, text_fb, has_url = analyze_text(post_text)
        
        image_score = 0
        image_fb = []
        is_nsfw = False
        detected_tags = {}
        
        # 画像分析
        if uploaded_file:
            image = Image.open(uploaded_file)
            
            # 画像があるだけでアルゴリズム上は有利 (+20点)
            image_score += 25 
            image_fb.append("✅ **メディア添付**: 画像/動画付き投稿はテキストのみより2倍以上拡散されやすくなります。")
            
            # CLIP解析
            detected_tags, is_nsfw = analyze_image_with_clip(image, target_tags)
            
            if is_nsfw:
                image_score = -100 # 強制的にスコアを下げる
                image_fb.append("⛔ **SHADOWBAN RISK**: AIがこの画像を「NSFW（センシティブ）」と判定する可能性が高いです。投稿は控えるか、修正が必要です。")
            else:
                image_fb.append("✅ **Safety Check**: AI判定は「Safe」です。")
                
                # ターゲット適合度チェック
                top_tag = max(target_tags.split(","), key=lambda t: detected_tags.get(t.strip(), 0))
                top_prob = detected_tags.get(top_tag.strip(), 0)
                
                if top_prob > 0.2: # 閾値
                    image_score += 15
                    image_fb.append(f"✅ **クラスター適合**: AIはこの画像を「{top_tag.strip()}」と強く認識しています。ターゲット層に届きやすいです。")
                else:
                    image_fb.append(f"⚠️ **認識不十分**: AIは指定されたキーワード（{top_tag.strip()}）の特徴をあまり検出できていません。プロンプトや構図を見直してください。")

        else:
            image_score -= 10
            image_fb.append("⚠️ **画像なし**: テキストのみの投稿は拡散力が低くなります。")

        # 総合スコア計算
        total_score = base_score + text_mod + image_score
        total_score = max(0, min(100, total_score)) # 0-100の範囲に収める
        
        # 結果表示
        if is_nsfw:
            st.error(f"スコア: 0 / 100 (危険)")
        elif total_score > 80:
            st.success(f"スコア: {total_score} / 100 (Excellent!)")
        elif total_score > 50:
            st.warning(f"スコア: {total_score} / 100 (Good)")
        else:
            st.error(f"スコア: {total_score} / 100 (Needs Improvement)")
            
        st.progress(total_score / 100)
        
        st.markdown("### 📋 詳細レポート")
        
        st.write("#### テキスト分析")
        for fb in text_fb:
            st.markdown(fb)
            
        st.write("#### 画像・メディア分析")
        for fb in image_fb:
            st.markdown(fb)
            
        if uploaded_file and not is_nsfw:
            st.write("#### 👁️ AIの認識確率 (CLIP)")
            # グラフ化
            st.bar_chart(detected_tags)
