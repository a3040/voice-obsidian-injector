const WS_URL = 'ws://127.0.0.1:9999';
let socket = new WebSocket(WS_URL);

socket.onopen = () => console.log('✅ 서버 연결 성공 (127.0.0.1:9999)');
socket.onerror = (err) => console.error('❌ 소켓 에러:', err);

socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    chrome.tabs.query({active: true, currentWindow: true}, (tabs) => {
        if (tabs[0] && tabs[0].id) {
            // content.js가 살아있는지 확인하며 던지기
            chrome.tabs.sendMessage(tabs[0].id, data, (response) => {
                if (chrome.runtime.lastError) {
                    console.warn("⚠️ 아직 이 탭에는 content.js가 준비되지 않았습니다 (새로고침 필요)");
                } else {
                    console.log("✅ content.js로 데이터 전달 완료!");
                }
            });
        }
    });
};

// content.js로부터의 요청 처리
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.type === "GET_LAST_TEXT") {
        socket.send(JSON.stringify({ type: "GET_LAST_TEXT" }));
    }
});
