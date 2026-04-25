# app.py - 完整版：首頁簡化 + 零件查詢 + 其他功能保留

import streamlit as st
import pandas as pd
import json
from datetime import datetime
import anthropic
from typing import Optional
import plotly.express as px
import plotly.graph_objects as go
from fuzzywuzzy import fuzz, process

# ==========================================
# 📚 知識庫定義
# ==========================================

MATERIAL_DB = {
    'aluminum': {'carbon_factor': 8.2, 'density': 2.7, 'source': 'ICCA 2023'},
    'aluminum_recycled': {'carbon_factor': 4.9, 'density': 2.7, 'source': 'ICCA 2023'},
    'pc': {'carbon_factor': 3.4, 'density': 1.2, 'source': 'Plastics Europe'},
    'fr-4': {'carbon_factor': 15.0, 'density': 1.85, 'source': 'IPC'},
    'li-ion': {'carbon_factor': 12.5, 'density': 2.0, 'source': 'ICCT'},
    'stainless_steel': {'carbon_factor': 3.5, 'density': 7.75, 'source': 'WSA'},
    'silicone': {'carbon_factor': 4.0, 'density': 1.1, 'source': 'Dow'},
    'copper': {'carbon_factor': 3.5, 'density': 8.96, 'source': 'ICMM'},
}

PROCESS_DB = {
    'cnc': {'energy_per_kg': 2.5, 'yield': 0.85, 'source': 'NIST'},
    'injection_molding': {'energy_per_kg': 1.8, 'yield': 0.95, 'source': 'PlasticsEurope'},
    'smt': {'energy_per_kg': 1.2, 'yield': 0.98, 'source': 'IPC'},
    'assembly': {'energy_per_kg': 0.5, 'yield': 0.99, 'source': 'Internal'},
    'stamping': {'energy_per_kg': 1.5, 'yield': 0.90, 'source': 'NIST'},
}

TRANSPORT_DB = {
    'truck': {'carbon_per_tkm': 0.100, 'source': 'DEFRA 2023'},
    'ship': {'carbon_per_tkm': 0.015, 'source': 'DEFRA 2023'},
    'air': {'carbon_per_tkm': 1.250, 'source': 'DEFRA 2023'},
}

# 零件庫
PARTS_DB = {
    'P001': {
        'name': '筒身',
        'weight_g': 150,
        'material': 'aluminum',
        'process': 'cnc',
        'origin': '台灣',
        'transport_mode': 'truck',
        'distance_km': 50,
        'quantity': 1,
    },
    'P002': {
        'name': '反光杯',
        'weight_g': 80,
        'material': 'aluminum',
        'process': 'stamping',
        'origin': '中國',
        'transport_mode': 'ship',
        'distance_km': 800,
        'quantity': 1,
    },
    'P003': {
        'name': '電池',
        'weight_g': 50,
        'material': 'li-ion',
        'process': 'assembly',
        'origin': '日本',
        'transport_mode': 'air',
        'distance_km': 2100,
        'quantity': 2,
    },
    'P004': {
        'name': 'LED 燈珠',
        'weight_g': 5,
        'material': 'fr-4',
        'process': 'smt',
        'origin': '台灣',
        'transport_mode': 'truck',
        'distance_km': 50,
        'quantity': 1,
    },
    'P005': {
        'name': '矽膠墊圈',
        'weight_g': 10,
        'material': 'silicone',
        'process': 'injection_molding',
        'origin': '台灣',
        'transport_mode': 'truck',
        'distance_km': 50,
        'quantity': 4,
    },
}

# ==========================================
# 🔧 核心計算函數
# ==========================================

def fuzzy_match_key(input_val, db_dict, threshold=80):
    """模糊匹配"""
    if not input_val:
        return None
    
    input_lower = str(input_val).lower().strip()
    
    if input_lower in db_dict:
        return input_lower
    
    matches = process.extract(input_lower, db_dict.keys(), scorer=fuzz.token_set_ratio)
    if matches and matches[0][1] >= threshold:
        return matches[0][0]
    
    return None

def calculate_part_carbon(part_data: dict) -> dict:
    """計算單個零件的碳排"""
    
    weight_kg = part_data['weight_g'] / 1000
    quantity = part_data.get('quantity', 1)
    
    # 材料碳排
    material_key = fuzzy_match_key(part_data['material'], MATERIAL_DB)
    if material_key:
        material_carbon = weight_kg * MATERIAL_DB[material_key]['carbon_factor']
        material_source = MATERIAL_DB[material_key]['source']
    else:
        material_carbon = weight_kg * 5.0
        material_source = 'Default'
    
    # 製程碳排
    process_key = fuzzy_match_key(part_data['process'], PROCESS_DB)
    if process_key:
        process_data = PROCESS_DB[process_key]
        actual_weight = weight_kg * quantity / process_data['yield']
        process_carbon = actual_weight * process_data['energy_per_kg']
        process_source = process_data['source']
    else:
        process_carbon = weight_kg * 1.0
        process_source = 'Default'
    
    # 物流碳排
    transport_key = fuzzy_match_key(part_data['transport_mode'], TRANSPORT_DB)
    distance_km = part_data.get('distance_km', 1000)
    if transport_key:
        transport_carbon = weight_kg * distance_km * TRANSPORT_DB[transport_key]['carbon_per_tkm']
        transport_source = TRANSPORT_DB[transport_key]['source']
    else:
        transport_carbon = weight_kg * distance_km * 0.1
        transport_source = 'Default'
    
    # 包裝碳排
    packaging_carbon = weight_kg * 0.3
    
    # 總碳排
    total_carbon = material_carbon + process_carbon + transport_carbon + packaging_carbon
    
    return {
        'material_carbon': material_carbon,
        'material_source': material_source,
        'process_carbon': process_carbon,
        'process_source': process_source,
        'transport_carbon': transport_carbon,
        'transport_source': transport_source,
        'packaging_carbon': packaging_carbon,
        'total_carbon': total_carbon,
        'material_key': material_key,
        'process_key': process_key,
        'transport_key': transport_key,
    }

def check_carbon_warning(total_carbon: float, threshold: float = 5.0) -> dict:
    """檢查碳排警示"""
    if total_carbon > threshold:
        return {
            'status': 'warning',
            'message': f'⚠️ 警告：碳排 {total_carbon:.2f} kgCO2e 超過閥值 {threshold} kgCO2e',
            'severity': 'high' if total_carbon > threshold * 1.5 else 'medium'
        }
    return {'status': 'ok', 'message': '✅ 碳排在合理範圍內'}

def get_material_alternatives(current_material: str, current_carbon: float) -> list:
    """獲取材料替換建議"""
    alternatives = []
    current_key = fuzzy_match_key(current_material, MATERIAL_DB)
    
    if not current_key:
        return alternatives
    
    current_factor = MATERIAL_DB[current_key]['carbon_factor']
    
    for mat_key, mat_data in MATERIAL_DB.items():
        if mat_key != current_key:
            carbon_diff = mat_data['carbon_factor'] - current_factor
            reduction_pct = (carbon_diff / current_factor) * 100
            
            alternatives.append({
                'material': mat_key,
                'carbon_factor': mat_data['carbon_factor'],
                'reduction_pct': reduction_pct,
                'source': mat_data['source'],
            })
    
    alternatives.sort(key=lambda x: x['reduction_pct'])
    return alternatives[:3]

def get_ai_recommendation(part_name: str, carbon_data: dict, alternatives: list, api_key: str) -> str:
    """使用 Claude 生成詳細建議"""
    
    client = anthropic.Anthropic(api_key=api_key)
    
    prompt = f"""你是一個綠色設計專家。根據以下零件的碳足跡數據，提供具體的材料替換建議。

【零件信息】
- 名稱: {part_name}
- 總碳排: {carbon_data['total_carbon']:.2f} kgCO2e
  - 材料碳排: {carbon_data['material_carbon']:.2f} kgCO2e ({carbon_data['material_carbon']/carbon_data['total_carbon']*100:.1f}%)
  - 製程碳排: {carbon_data['process_carbon']:.2f} kgCO2e ({carbon_data['process_carbon']/carbon_data['total_carbon']*100:.1f}%)
  - 物流碳排: {carbon_data['transport_carbon']:.2f} kgCO2e ({carbon_data['transport_carbon']/carbon_data['total_carbon']*100:.1f}%)
  - 包裝碳排: {carbon_data['packaging_carbon']:.2f} kgCO2e ({carbon_data['packaging_carbon']/carbon_data['total_carbon']*100:.1f}%)

【可替換材料】
{json.dumps(alternatives, indent=2, ensure_ascii=False)}

請提供：
1. 最推薦的材料替換方案
2. 預期的減碳效果
3. 實施難度評估（易/中/難）
4. 相關的綠色認證建議
5. 供應商選擇建議

回答要簡潔專業。"""
    
    message = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    
    return message.content[0].text

# ==========================================
# 🎨 Streamlit 頁面
# ==========================================

def show_home():
    st.markdown("""
    # 🌱 OPS 碳足跡 AI 工具
    
    企業級碳足跡管理與綠色設計推薦平台
    
    ## 核心功能
    
    ### 1️⃣ 零件查詢引擎
    - 模糊搜尋零件編號或名稱
    - 自動計算碳足跡分解
    - 來源引用與可靠性驗證
    
    ### 2️⃣ BOM 快速估算
    - 一鍵上傳物料清單
    - 自動對接碳係數庫
    - 補充製程、物流、包裝預估
    
    ### 3️⃣ 綠色設計推薦
    - 智慧識別高碳排零件
    - 推薦低碳替代方案
    - 鎖定關鍵規格，優化剩餘空間
    
    ### 4️⃣ AI 助手
    - 多輪對話支援
    - 情境模擬與對比分析
    - 法規遵循檢查
    """)

def show_part_query(api_key: str, threshold: float):
    """零件查詢頁面"""
    st.header("🔍 零件查詢")
    st.markdown("輸入零件編號，快速查詢碳足跡並獲得材料替換建議")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("### 🔍 零件查詢")
        
        search_input = st.text_input(
            "輸入零件編號或名稱（支援模糊搜尋）",
            placeholder="例如：P001 或 筒身"
        )
        
        if search_input:
            search_lower = search_input.lower()
            matched_parts = {}
            
            for part_id, part_info in PARTS_DB.items():
                if search_lower in part_id.lower():
                    matched_parts[part_id] = part_info
                elif search_lower in part_info['name'].lower():
                    matched_parts[part_id] = part_info
                else:
                    similarity = fuzz.token_set_ratio(search_lower, part_info['name'].lower())
                    if similarity > 70:
                        matched_parts[part_id] = part_info
            
            if matched_parts:
                selected_part_id = st.selectbox(
                    "選擇零件",
                    list(matched_parts.keys()),
                    format_func=lambda x: f"{x} - {matched_parts[x]['name']}"
                )
                
                part_data = PARTS_DB[selected_part_id]
                carbon_data = calculate_part_carbon(part_data)
                
                st.divider()
                
                # 零件信息
                st.markdown(f"### 📦 {selected_part_id} - {part_data['name']}")
                
                info_col1, info_col2, info_col3 = st.columns(3)
                info_col1.metric("重量", f"{part_data['weight_g']} g")
                info_col2.metric("材質", part_data['material'])
                info_col3.metric("製程", part_data['process'])
                
                st.markdown("---")
                
                # 碳排分解
                st.markdown("### 📊 碳足跡分解")
                
                fig = go.Figure(data=[go.Pie(
                    labels=['材料', '製程', '物流', '包裝'],
                    values=[
                        carbon_data['material_carbon'],
                        carbon_data['process_carbon'],
                        carbon_data['transport_carbon'],
                        carbon_data['packaging_carbon']
                    ],
                    marker=dict(colors=['#3b82f6', '#ef4444', '#f59e0b', '#10b981'])
                )])
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)
                
                # 詳細數據
                st.markdown("### 📋 詳細碳排數據")
                
                data_col1, data_col2 = st.columns(2)
                
                with data_col1:
                    st.metric(
                        "材料碳排",
                        f"{carbon_data['material_carbon']:.4f} kgCO2e",
                        f"來源: {carbon_data['material_source']}"
                    )
                    st.metric(
                        "製程碳排",
                        f"{carbon_data['process_carbon']:.4f} kgCO2e",
                        f"來源: {carbon_data['process_source']}"
                    )
                
                with data_col2:
                    st.metric(
                        "物流碳排",
                        f"{carbon_data['transport_carbon']:.4f} kgCO2e",
                        f"來源: {carbon_data['transport_source']}"
                    )
                    st.metric(
                        "包裝碳排",
                        f"{carbon_data['packaging_carbon']:.4f} kgCO2e",
                        "預估值"
                    )
                
                st.divider()
                
                # 碳排警示
                st.markdown("### ⚠️ 碳排警示")
                
                warning = check_carbon_warning(carbon_data['total_carbon'], threshold)
                
                if warning['status'] == 'warning':
                    st.error(warning['message'])
                else:
                    st.success(warning['message'])
                
                st.metric(
                    "總碳排",
                    f"{carbon_data['total_carbon']:.4f} kgCO2e",
                    f"閥值: {threshold} kgCO2e"
                )
                
                st.divider()
                
                # 材料替換建議
                st.markdown("### 💡 材料替換建議")
                
                alternatives = get_material_alternatives(
                    carbon_data['material_key'],
                    carbon_data['material_carbon']
                )
                
                if alternatives:
                    for i, alt in enumerate(alternatives, 1):
                        with st.expander(f"方案 {i}: {alt['material'].upper()} (減碳 {abs(alt['reduction_pct']):.1f}%)"):
                            col1, col2, col3 = st.columns(3)
                            col1.metric("碳係數", f"{alt['carbon_factor']:.2f}")
                            col2.metric("減碳幅度", f"{abs(alt['reduction_pct']):.1f}%")
                            col3.metric("來源", alt['source'])
                
                st.divider()
                
                # AI 詳細建議
                if api_key:
                    st.markdown("### 🤖 AI 詳細建議")
                    
                    if st.button("生成 AI 建議", key="ai_recommend"):
                        with st.spinner("生成建議中..."):
                            try:
                                ai_rec = get_ai_recommendation(
                                    part_data['name'],
                                    carbon_data,
                                    alternatives,
                                    api_key
                                )
                                st.markdown(ai_rec)
                            except Exception as e:
                                st.error(f"❌ 生成失敗: {str(e)}")
                else:
                    st.info("💡 輸入 API Key 以獲得 AI 詳細建議")
            
            else:
                st.warning(f"❌ 找不到符合 '{search_input}' 的零件")
    
    with col2:
        st.markdown("### 📚 使用說明")
        st.markdown("""
        1. **輸入零件編號或名稱**
           - 支援模糊搜尋
           - 例如：P001、筒身
        
        2. **查看碳足跡分解**
           - 材料、製程、物流、包裝
           - 每項都有來源引用
        
        3. **檢查碳排警示**
           - 超過閥值自動警告
           - 可在側邊欄調整閥值
        
        4. **獲得替換建議**
           - 推薦低碳材料
           - AI 詳細分析
        """)

def show_bom_estimation(api_key: str):
    """BOM 估算頁面"""
    st.header("📊 BOM 快速估算")
    
    st.markdown("""
    上傳物料清單 (CSV/Excel)，系統自動計算碳足跡。
    
    **必需欄位：**
    - part_number, part_name, quantity, weight_g
    - material, process, origin, transport_mode, distance_km
    """)
    
    uploaded_file = st.file_uploader("上傳 BOM 檔案", type=['csv', 'xlsx'])
    
    if uploaded_file:
        try:
            if uploaded_file.name.endswith('.csv'):
                bom_df = pd.read_csv(uploaded_file)
            else:
                bom_df = pd.read_excel(uploaded_file)
            
            st.success("✅ 檔案上傳成功")
            
            # 簡單的 BOM 估算
            result_rows = []
            for idx, row in bom_df.iterrows():
                part_data = {
                    'weight_g': row.get('weight_g', 0),
                    'material': row.get('material', ''),
                    'process': row.get('process', ''),
                    'transport_mode': row.get('transport_mode', ''),
                    'distance_km': row.get('distance_km', 1000),
                    'quantity': row.get('quantity', 1),
                }
                carbon = calculate_part_carbon(part_data)
                result_rows.append({
                    'part_number': row.get('part_number', ''),
                    'part_name': row.get('part_name', ''),
                    **carbon
                })
            
            result_df = pd.DataFrame(result_rows)
            
            st.markdown("### 📊 碳足跡估算結果")
            st.dataframe(result_df, use_container_width=True)
            
            # 統計
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("總碳排", f"{result_df['total_carbon'].sum():.2f} kgCO2e")
            col2.metric("零件數", len(result_df))
            col3.metric("平均單件碳排", f"{result_df['total_carbon'].mean():.2f} kgCO2e")
            col4.metric("最高碳排零件", f"{result_df['total_carbon'].max():.2f} kgCO2e")
            
            # 視覺化
            fig = px.pie(
                values=result_df['total_carbon'],
                names=result_df['part_name'],
                title="零件碳排分佈"
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # 下載
            csv = result_df.to_csv(index=False)
            st.download_button("📥 下載結果", csv, "bom_carbon_estimation.csv")
            
        except Exception as e:
            st.error(f"❌ 錯誤: {str(e)}")

def show_design_recommendations(api_key: str):
    """設計建議頁面"""
    st.header("💡 綠色設計推薦")
    
    st.markdown("""
    基於 BOM 數據，系統自動識別高碳排零件並推薦優化方案。
    """)
    
    uploaded_file = st.file_uploader("上傳 BOM 檔案", type=['csv', 'xlsx'], key="design_rec")
    
    if uploaded_file:
        try:
            if uploaded_file.name.endswith('.csv'):
                bom_df = pd.read_csv(uploaded_file)
            else:
                bom_df = pd.read_excel(uploaded_file)
            
            # 估算碳足跡
            result_rows = []
            for idx, row in bom_df.iterrows():
                part_data = {
                    'weight_g': row.get('weight_g', 0),
                    'material': row.get('material', ''),
                    'process': row.get('process', ''),
                    'transport_mode': row.get('transport_mode', ''),
                    'distance_km': row.get('distance_km', 1000),
                    'quantity': row.get('quantity', 1),
                }
                carbon = calculate_part_carbon(part_data)
                result_rows.append({
                    'part_number': row.get('part_number', ''),
                    'part_name': row.get('part_name', ''),
                    **carbon
                })
            
            result_df = pd.DataFrame(result_rows)
            
            # 鎖定規格
            st.markdown("### 🔒 鎖定不可變動的規格")
            locked_parts = st.multiselect(
                "選擇要鎖定的零件",
                result_df['part_number'].tolist()
            )
            
            # 識別高碳排零件
            high_carbon_threshold = result_df['total_carbon'].mean() * 1.5
            high_carbon_parts = result_df[result_df['total_carbon'] > high_carbon_threshold]
            
            if len(high_carbon_parts) > 0:
                st.markdown("### 📋 高碳排零件優化建議")
                
                for idx, row in high_carbon_parts.iterrows():
                    if row['part_number'] not in locked_parts:
                        with st.expander(f"🔴 {row['part_name']} - {row['total_carbon']:.2f} kgCO2e"):
                            st.write(f"**編號**: {row['part_number']}")
                            st.write(f"**當前碳排**: {row['total_carbon']:.2f} kgCO2e")
                            
                            # 材料替換建議
                            alternatives = get_material_alternatives(
                                row['material_key'],
                                row['material_carbon']
                            )
                            
                            if alternatives:
                                st.write("**推薦替換材料**:")
                                for alt in alternatives[:2]:
                                    reduction = row['material_carbon'] * (abs(alt['reduction_pct']) / 100)
                                    st.write(f"- {alt['material'].upper()}: 減碳 {reduction:.2f} kgCO2e ({abs(alt['reduction_pct']):.1f}%)")
            else:
                st.success("✅ 所有零件碳排均在合理範圍內")
        
        except Exception as e:
            st.error(f"❌ 錯誤: {str(e)}")

def show_ai_copilot(api_key: str):
    """AI 助手頁面"""
    st.header("🤖 AI 助手")
    
    st.markdown("""
    與 AI 助手進行多輪對話，獲取碳足跡相關的專業建議。
    """)
    
    if not api_key:
        st.error("❌ 請在側邊欄輸入 API Key")
        return
    
    # 初始化對話歷史
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    
    # 顯示對話歷史
    for message in st.session_state.messages:
        with st.chat_message(message['role']):
            st.markdown(message['content'])
    
    # 用戶輸入
    user_input = st.chat_input("輸入你的問題...")
    
    if user_input:
        st.session_state.messages.append({'role': 'user', 'content': user_input})
        with st.chat_message('user'):
            st.markdown(user_input)
        
        with st.spinner("思考中..."):
            try:
                client = anthropic.Anthropic(api_key=api_key)
                response = client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=2048,
                    messages=[
                        {"role": "user", "content": user_input}
                    ]
                )
                
                ai_response = response.content[0].text
                st.session_state.messages.append({'role': 'assistant', 'content': ai_response})
                with st.chat_message('assistant'):
                    st.markdown(ai_response)
            except Exception as e:
                st.error(f"❌ 錯誤: {str(e)}")

# ==========================================
# 🎨 主應用
# ==========================================

def main():
    st.set_page_config(
        page_title="OPS 碳足跡 AI 工具",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("🌱 OPS 碳足跡 AI 工具")
    
    # 側邊欄
    with st.sidebar:
        st.header("⚙️ 設定")
        api_key = st.text_input("輸入 Anthropic API Key", type="password", value=st.secrets.get("ANTHROPIC_API_KEY", ""))
        threshold = st.slider("碳排警示閥值 (kgCO2e)", 1.0, 10.0, 5.0, 0.5)
        
        st.divider()
        st.header("📋 功能選單")
        page = st.radio(
            "選擇功能",
            ["🏠 首頁", "🔍 零件查詢", "📊 BOM 估算", "💡 設計建議", "🤖 AI 助手"]
        )
    
    # 頁面路由
    if page == "🏠 首頁":
        show_home()
    elif page == "🔍 零件查詢":
        show_part_query(api_key, threshold)
    elif page == "📊 BOM 估算":
        show_bom_estimation(api_key)
    elif page == "💡 設計建議":
        show_design_recommendations(api_key)
    elif page == "🤖 AI 助手":
        show_ai_copilot(api_key)

if __name__ == "__main__":
    main()
