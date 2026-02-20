/*const socket = new WebSocket('ws://localhost:9999');

socket.onopen = () => console.log('파이썬 서버와 연결되었습니다!');
*/

// 입력창(Input/Textarea/Editable)에 포커스가 잡힐 때 이벤트 발생
document.addEventListener('focusin', (e) => {
    const el = e.target;
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable) {
        console.log("🎯 입력창 포커스 감지! waiting data from background..");
        // 서버에 '가져오기' 요청 전송
        //socket.send(JSON.stringify({ type: "GET_LAST_TEXT" }));
	chrome.runtime.sendMessage({type:"GET_LAST_TEXT"});
    }
}, true);

// browser 또는 chrome 둘 다 사용 가능하지만 파이어폭스라면 browser 권장
(browser || chrome).runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === "INSERT_TEXT") {
        const el = document.activeElement;

        if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)) {
            console.log("📥 데이터 삽입 중:", message.text);

            if (el.isContentEditable) {
                el.innerText = message.text;
            } else {
                el.value = message.text;
            }

            // 이벤트 발생 (React 등 프레임워크 대응)
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        } else {
            console.warn("⚠️ 포커스된 입력창이 없습니다.");
        }
    }
    // 비동기 응답을 위해 true 반환 (필요 시)
    return true;
});
