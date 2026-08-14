import { writeFile } from 'node:fs/promises';

const port = process.env.CDP_PORT || '9224';
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const targets = await fetch(`http://127.0.0.1:${port}/json`).then((response) => response.json());
const page = targets.find((target) => target.type === 'page');
if (!page) throw new Error('Không tìm thấy tab Chrome để kiểm tra.');

const socket = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener('open', resolve, { once: true });
  socket.addEventListener('error', reject, { once: true });
});

let nextId = 1;
const pending = new Map();
socket.addEventListener('message', (event) => {
  const message = JSON.parse(event.data);
  if (!message.id || !pending.has(message.id)) return;
  const { resolve, reject } = pending.get(message.id);
  pending.delete(message.id);
  if (message.error) reject(new Error(message.error.message));
  else resolve(message.result);
});

const send = (method, params = {}) => new Promise((resolve, reject) => {
  const id = nextId++;
  pending.set(id, { resolve, reject });
  socket.send(JSON.stringify({ id, method, params }));
});

const evaluate = async (expression) => {
  const result = await send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
  return result.result.value;
};

await send('Runtime.enable');
await send('Page.enable');
await sleep(Number(process.env.PRE_HOVER_WAIT_MS || 2500));

const visibleTargets = await evaluate(`(() =>
  [...document.querySelectorAll('[data-branch-target]')]
    .map((target) => {
      const rect = target.getBoundingClientRect();
      return {
        label: target.getAttribute('data-branch-target'),
        display: getComputedStyle(target).display,
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height,
      };
    })
    .filter((target) => target.display !== 'none' && target.width > 0 && target.height > 0)
)()`);

if (!visibleTargets.length) throw new Error('Không có vùng hover beacon nào hiển thị trong viewport.');

const target = visibleTargets[0];
const x = target.x + target.width / 2;
const y = target.y + target.height / 2;
const receiver = await evaluate(`document.elementFromPoint(${JSON.stringify(x)}, ${JSON.stringify(y)})?.tagName || ''`);
if (receiver !== 'CANVAS') throw new Error(`Tọa độ beacon đang bị ${receiver || 'không có phần tử'} che phủ.`);
await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y });
await sleep(700);
await evaluate(`new Promise((resolve) => {
  const image = document.querySelector('[data-branch-card] img');
  if (!image || (image.complete && image.naturalWidth)) return resolve(true);
  const finish = () => resolve(true);
  image.addEventListener('load', finish, { once: true });
  image.addEventListener('error', finish, { once: true });
  setTimeout(finish, 3000);
})`);

const card = await evaluate(`(() => {
  const card = document.querySelector('[data-branch-card]');
  const image = card?.querySelector('img');
  const rect = card?.getBoundingClientRect();
  const style = card ? getComputedStyle(card) : null;
  const topElement = rect ? document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2) : null;
  return {
    exists: Boolean(card),
    text: card?.textContent?.replace(/\\s+/g, ' ').trim() || '',
    imageSrc: image?.getAttribute('src') || '',
    imageLoaded: Boolean(image?.complete && image?.naturalWidth),
    rect: rect ? { x: rect.x, y: rect.y, width: rect.width, height: rect.height } : null,
    display: style?.display || '',
    visibility: style?.visibility || '',
    opacity: style?.opacity || '',
    zIndex: style?.zIndex || '',
    topElement: topElement ? topElement.tagName + '.' + topElement.className : '',
  };
})()`);

if (!card.exists) throw new Error(`Hover ${target.label} nhưng card chi nhánh không xuất hiện.`);
if (!card.text.includes('ĐANG HOẠT ĐỘNG')) throw new Error(`Card thiếu trạng thái hoạt động: ${card.text}`);
if (!card.imageSrc || !card.imageLoaded) throw new Error(`Ảnh card chưa tải thành công: ${card.imageSrc}`);
if (!card.rect || card.rect.width < 200 || card.rect.height < 120 || card.rect.height > 260 || card.rect.x < 0 || card.rect.y < 0) {
  throw new Error(`Card tồn tại nhưng kích thước/vị trí không thể nhìn thấy: ${JSON.stringify(card.rect)}`);
}

if (process.env.HOVER_SCREENSHOT) {
  await sleep(250);
  const screenshot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  await writeFile(process.env.HOVER_SCREENSHOT, Buffer.from(screenshot.data, 'base64'));
}

await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: 8, y: 8 });
await sleep(350);
const cardAfterLeave = await evaluate(`Boolean(document.querySelector('[data-branch-card]'))`);
if (cardAfterLeave) throw new Error('Card vẫn còn hiển thị sau khi rời beacon.');

console.log(JSON.stringify({
  result: 'PASS',
  testedTarget: target.label,
  pointerReceiver: receiver,
  visibleBeaconCount: visibleTargets.length,
  card,
  cardHiddenAfterLeave: !cardAfterLeave,
}, null, 2));

socket.close();
