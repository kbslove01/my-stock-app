import streamlit as st
import pandas as pd
from pykrx import stock
import datetime as dt
import plotly.graph_objects as go

# -----------------------------------------------------------------------------
# [페이지 기본 설정]
# -----------------------------------------------------------------------------
st.set_page_config(page_title="국내주식 가치투자 검색기", layout="wide")
st.title("📊 국내주식 조건 검색 & 이동평균선 차트 대시보드")
st.write("오후 4~5시 거래소 정산 시간에도 에러 없이 작동하는 안정화 버전입니다.")

# -----------------------------------------------------------------------------
# [데이터 수집 및 필터링 함수 (오류 완벽 방어형)]
# -----------------------------------------------------------------------------
@st.cache_data(ttl=3600)
def get_and_filter_stocks(max_price, max_pbr, max_per, min_div):
    kst = dt.timezone(dt.timedelta(hours=9))
    check_date = dt.datetime.now(kst)

    # 1. 주가 데이터 확보 (가장 최근 영업일 역추적)
    df_price = pd.DataFrame()
    price_date = check_date
    for _ in range(7):
        today_str = price_date.strftime("%Y%m%d")
        try:
            df_price = stock.get_market_ohlcv(today_str, market="ALL")
            if not df_price.empty and '종가' in df_price.columns:
                break
        except:
            pass
        price_date -= dt.timedelta(days=1)

    if df_price.empty:
        st.error("한국거래소(KRX)에서 주가 데이터를 가져오지 못했습니다.")
        return pd.DataFrame()

    # 2. 재무 데이터 확보 (주가 데이터가 존재하는 날짜부터 역추적)
    df_fundamental = pd.DataFrame()
    fund_date = price_date 
    for _ in range(7):
        fund_str = fund_date.strftime("%Y%m%d")
        try:
            df_fundamental = stock.get_market_fundamental(fund_str, market="ALL")
            if not df_fundamental.empty and 'PBR' in df_fundamental.columns:
                break
        except:
            pass
        fund_date -= dt.timedelta(days=1)

    if df_fundamental.empty:
        st.error("한국거래소(KRX)에서 재무 지표 데이터를 가져오지 못했습니다.")
        return pd.DataFrame()

    # 3. 데이터 병합 및 정제
    try:
        df = pd.merge(df_price, df_fundamental, left_index=True, right_index=True)
        df['종목명'] = df.index.map(lambda x: stock.get_market_ticker_name(x))
        
        # PBR 0이거나 누락된 비정상 데이터 제외
        df = df[df['PBR'] > 0]

        # 조건 필터링
        condition = True
        if max_price > 0: condition &= (df['종가'] <= max_price)
        if max_pbr > 0: condition &= (df['PBR'] <= max_pbr)
        if max_per > 0: condition &= (df['PER'] <= max_per)
        if min_div > 0: condition &= (df['DIV'] >= min_div)

        result = df[condition][['종목명', '종가', 'PBR', 'PER', 'DIV', '거래량']]
        return result.sort_values(by='PBR', ascending=True)
        
    except Exception as e:
        st.error(f"데이터 병합 중 오류 발생: {e}")
        return pd.DataFrame()

# -----------------------------------------------------------------------------
# [차트 생성 함수 (5일, 20일, 60일 이평선 포함)]
# -----------------------------------------------------------------------------
def draw_analysis_chart(ticker_code, ticker_name):
    kst = dt.timezone(dt.timedelta(hours=9))
    today_str = dt.datetime.now(kst).strftime("%Y%m%d")
    start_str = (dt.datetime.now(kst) - dt.timedelta(days=500)).strftime("%Y%m%d")

    df_chart = stock.get_market_ohlcv(start_str, today_str, ticker_code)
    if df_chart.empty:
        st.warning("차트 데이터를 불러올 수 없습니다.")
        return None

    # 이동평균선 계산
    df_chart['MA5'] = df_chart['종가'].rolling(window=5).mean()
    df_chart['MA20'] = df_chart['종가'].rolling(window=20).mean()
    df_chart['MA60'] = df_chart['종가'].rolling(window=60).mean()

    # 차트 그리기
    fig = go.Figure(data=[
        go.Candlestick(x=df_chart.index, open=df_chart['시가'], high=df_chart['고가'], low=df_chart['저가'], close=df_chart['종가'], name='주가(봉)', increasing_line_color='red', decreasing_line_color='blue'),
        go.Scatter(x=df_chart.index, y=df_chart['MA5'], name='5일선', line=dict(color='green', width=1.2)),
        go.Scatter(x=df_chart.index, y=df_chart['MA20'], name='20일선', line=dict(color='orange', width=1.2)),
        go.Scatter(x=df_chart.index, y=df_chart['MA60'], name='60일선', line=dict(color='purple', width=1.2))
    ])
    
    # 줌(Zoom) 설정: 데이터가 120일 미만이면 처음부터, 이상이면 최근 120일만 표시
    zoom_start = df_chart.index[-120] if len(df_chart) > 120 else df_chart.index[0]
    
    fig.update_layout(
        title=f"📈 {ticker_name} ({ticker_code}) 기술적 분석 차트", 
        yaxis_title='주가 (원)', 
        xaxis_rangeslider_visible=False, 
        xaxis=dict(range=[zoom_start, df_chart.index[-1]]), 
        height=600, 
        template="plotly_white"
    )
    return fig

# -----------------------------------------------------------------------------
# [UI 레이아웃 구성]
# -----------------------------------------------------------------------------
st.sidebar.header("🔍 검색 조건 설정")
st.sidebar.write("0을 입력하면 해당 조건은 무시됩니다.")

inp_price = st.sidebar.number_input("최대 가격 (원)", min_value=0, value=50000, step=5000)
inp_pbr = st.sidebar.number_input("최대 PBR (배)", min_value=0.0, value=0.8, step=0.1)
inp_per = st.sidebar.number_input("최대 PER (배)", min_value=0.0, value=0.0, step=1.0)
inp_div = st.sidebar.number_input("최소 배당수익률 (%)", min_value=0.0, value=3.0, step=0.5)

btn_search = st.sidebar.button("🚀 조건으로 주식 검색", use_container_width=True)

col_table, col_chart = st.columns([1, 1])

# 세션 상태 유지
if "search_clicked" not in st.session_state: st.session_state.search_clicked = False
if "stock_data" not in st.session_state: st.session_state.stock_data = pd.DataFrame()

# 검색 버튼 클릭 시
if btn_search:
    st.session_state.search_clicked = True
    with st.spinner("KRX 데이터를 분석 중입니다..."):
        st.session_state.stock_data = get_and_filter_stocks(inp_price, inp_pbr, inp_per, inp_div)

# 결과 화면 렌더링
if st.session_state.search_clicked:
    df_result = st.session_state.stock_data
    with col_table:
        st.subheader(f"✅ 검색 결과 ({len(df_result)}개 종목)")
        if not df_result.empty:
            st.write("💡 아래 테이블에서 종목을 선택하세요.")
            event = st.dataframe(df_result, use_container_width=True, height=550, on_select="rerun", selection_mode="single-row")
            selected_rows = event.get("selection", {}).get("rows", [])
            
            if selected_rows:
                idx = selected_rows[0]
                ticker_code = df_result.index[idx]
                ticker_name = df_result.iloc[idx]['종목명']
                with col_chart:
                    chart_fig = draw_analysis_chart(ticker_code, ticker_name)
                    if chart_fig: st.plotly_chart(chart_fig, use_container_width=True)
            else:
                with col_chart: st.info("👈 왼쪽 표에서 종목을 클릭하시면 이동평균선 차트가 나타납니다.")
        else: 
            st.warning("조건을 만족하는 주식이 없습니다.")
else:
    with col_table: 
        st.info("👈 왼쪽에서 조건을 입력한 후 [조건으로 주식 검색] 버튼을 눌러주세요.")
