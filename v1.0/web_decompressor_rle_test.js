// RLEデコード（バイト単位）: [値, 回数, 値, 回数, ...] → 展開
function rleDecode(data) {
    if (data.length % 2 !== 0) {
        throw new Error('RLEデータ長が不正です');
    }
    const out = [];
    for (let i = 0; i < data.length; i += 2) {
        const value = data[i];
        const count = data[i + 1];
        for (let j = 0; j < count; j++) {
            out.push(value);
        }
    }
    return new Uint8Array(out);
}

// テスト用データ: [0x41, 0x03, 0x42, 0x02] → [0x41, 0x41, 0x41, 0x42, 0x42]
const testData = new Uint8Array([0x41, 0x03, 0x42, 0x02]);
const decoded = rleDecode(testData);
console.log('デコード結果:', decoded);
console.log('デコード結果(文字列):', String.fromCharCode(...decoded));
// 期待値: "AAABB" 