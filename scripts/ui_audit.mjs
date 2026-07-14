import fs from "node:fs/promises";

const CDP_HOST = "http://127.0.0.1:9224";
const APP_URL = "http://127.0.0.1:5173";
const outputDir = new URL("../reports/ui-audit/", import.meta.url);
await fs.mkdir(outputDir, { recursive: true });

const pages = await fetch(`${CDP_HOST}/json/list`).then((response) =>
  response.json(),
);
const page = pages.find((item) => item.type === "page");
if (!page?.webSocketDebuggerUrl) {
  throw new Error("Chrome debugging page was not found.");
}

const socket = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});

let requestId = 0;
const pending = new Map();
const runtimeErrors = [];
const consoleErrors = [];

socket.addEventListener("message", (event) => {
  const message = JSON.parse(event.data);
  if (message.id && pending.has(message.id)) {
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) reject(new Error(message.error.message));
    else resolve(message.result);
    return;
  }
  if (message.method === "Runtime.exceptionThrown") {
    runtimeErrors.push(
      message.params.exceptionDetails?.text || "Unknown runtime exception",
    );
  }
  if (
    message.method === "Runtime.consoleAPICalled" &&
    message.params.type === "error"
  ) {
    consoleErrors.push(
      message.params.args
        .map((argument) => argument.value || argument.description || "")
        .join(" "),
    );
  }
});

function send(method, params = {}) {
  requestId += 1;
  const id = requestId;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });
}

async function evaluate(expression) {
  const result = await send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.text);
  }
  return result.result?.value;
}

async function waitFor(expression, timeout = 12_000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    if (await evaluate(`Boolean(${expression})`)) return;
    await new Promise((resolve) => setTimeout(resolve, 120));
  }
  throw new Error(`Timed out waiting for: ${expression}`);
}

async function screenshot(name) {
  const result = await send("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: false,
  });
  await fs.writeFile(
    new URL(name, outputDir),
    Buffer.from(result.data, "base64"),
  );
}

async function setViewport(width, height, mobile = false) {
  await send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile,
    screenWidth: width,
    screenHeight: height,
  });
}

await send("Page.enable");
await send("Runtime.enable");
await setViewport(1440, 900);
await send("Page.navigate", { url: APP_URL });
await waitFor("document.readyState === 'complete'");
await waitFor("document.querySelector('.auth-shell')");
await screenshot("01-auth-desktop.png");

const email = `ui-audit-${Date.now()}@local.test`;
await evaluate(`
  (() => {
    [...document.querySelectorAll('.auth-tabs button')]
      .find((button) => button.textContent.includes('რეგისტრაცია'))
      ?.click();
  })()
`);
await waitFor("document.querySelector('input[autocomplete=\"name\"]')");
await evaluate(`
  (() => {
    const setValue = (selector, value) => {
      const input = document.querySelector(selector);
      const prototype = input instanceof HTMLInputElement
        ? HTMLInputElement.prototype
        : HTMLTextAreaElement.prototype;
      Object.getOwnPropertyDescriptor(prototype, 'value').set.call(input, value);
      input.dispatchEvent(new Event('input', { bubbles: true }));
    };
    setValue('input[autocomplete="name"]', 'UI Audit User');
    setValue('input[autocomplete="email"]', ${JSON.stringify(email)});
    const passwords = document.querySelectorAll('input[type="password"]');
    passwords.forEach((input) => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')
        .set.call(input, 'Audit-pass-123');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    document.querySelector('.auth-form').requestSubmit();
  })()
`);
await waitFor("document.querySelector('.app-shell')", 20_000);
await waitFor("!document.querySelector('.session-loading')");
await screenshot("02-dashboard-desktop.png");
await evaluate(
  `document.querySelector('button[aria-label="ღია თემაზე გადასვლა"]').click()`,
);
await waitFor("document.documentElement.dataset.theme === 'light'");
await screenshot("02b-dashboard-light.png");
await evaluate(
  `document.querySelector('button[aria-label="მუქ თემაზე გადასვლა"]').click()`,
);
await waitFor("document.documentElement.dataset.theme === 'dark'");

const desktopMetrics = await evaluate(`
  (() => ({
    viewport: [innerWidth, innerHeight],
    documentWidth: document.documentElement.scrollWidth,
    bodyWidth: document.body.scrollWidth,
    heading: document.querySelector('.welcome-copy h1')?.innerText || '',
    suggestionCount: document.querySelectorAll('.suggestion-card').length,
    suggestionOverflow: [...document.querySelectorAll('.suggestion-card')]
      .some((card) => card.scrollWidth > card.clientWidth + 1),
    buttonsWithoutNames: [...document.querySelectorAll('button')]
      .filter((button) => !button.innerText.trim() && !button.getAttribute('aria-label') && !button.title)
      .map((button) => button.outerHTML.slice(0, 240)),
  }))()
`);

await evaluate(`
  (() => {
    const textarea = document.querySelector('#chat-message');
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')
      .set.call(textarea, 'გამარჯობა');
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    document.querySelector('.composer').requestSubmit();
  })()
`);
await waitFor(
  "document.querySelector('.message.assistant .message-content')?.textContent.trim().length > 0",
  20_000,
);
await screenshot("03-chat-desktop.png");

await evaluate(
  `document.querySelector('button[aria-label="წინა საუბრები"]').click()`,
);
await waitFor("document.querySelector('.history-drawer.is-open')");
const drawerOpenMetrics = await evaluate(`
  (() => {
    const drawer = document.querySelector('.history-drawer');
    return {
      ariaHidden: drawer.getAttribute('aria-hidden'),
      inert: drawer.inert,
      focusedElement: document.activeElement?.type || document.activeElement?.tagName,
    };
  })()
`);
await screenshot("04-history-desktop.png");
await evaluate(
  `document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))`,
);
await waitFor("!document.querySelector('.history-drawer.is-open')");
const drawerClosedMetrics = await evaluate(`
  (() => {
    const drawer = document.querySelector('.history-drawer');
    return {
      ariaHidden: drawer.getAttribute('aria-hidden'),
      inert: drawer.inert,
    };
  })()
`);

await evaluate(
  `document.querySelector('button[aria-label="პროფილის გახსნა"]').click()`,
);
await waitFor("document.querySelector('.profile-page')");
await screenshot("05-profile-desktop.png");

await setViewport(390, 844, true);
await new Promise((resolve) => setTimeout(resolve, 250));
await screenshot("06-profile-mobile.png");
await evaluate(`document.querySelector('.profile-back').click()`);
await waitFor("document.querySelector('.chat-workspace')");
await screenshot("07-chat-mobile.png");

const mobileMetrics = await evaluate(`
  (() => {
    const tooSmall = [...document.querySelectorAll('button:not([disabled]), a[href], input, select, textarea')]
      .map((element) => {
        const rect = element.getBoundingClientRect();
        return {
          label: element.getAttribute('aria-label') || element.title || element.innerText.trim().slice(0, 40) || element.tagName,
          width: Math.round(rect.width),
          height: Math.round(rect.height),
        };
      })
      .filter((item) => item.width > 0 && item.height > 0 && (item.width < 44 || item.height < 44));
    return {
      viewport: [innerWidth, innerHeight],
      documentWidth: document.documentElement.scrollWidth,
      bodyWidth: document.body.scrollWidth,
      tooSmall,
      headingOverflow: (() => {
        const heading = document.querySelector('.welcome-copy h1');
        return heading ? heading.scrollWidth > heading.clientWidth + 1 : false;
      })(),
    };
  })()
`);

await evaluate(
  `document.querySelector('button[aria-label="პროფილის გახსნა"]').click()`,
);
await waitFor("document.querySelector('.profile-page')");
await evaluate(`document.querySelector('.account-section .data-action.danger').click()`);
await waitFor("document.querySelector('.auth-shell')");
await screenshot("08-auth-mobile.png");
const authMobileMetrics = await evaluate(`
  (() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: innerWidth,
    tooSmall: [...document.querySelectorAll('button:not([disabled]), input')]
      .map((element) => {
        const rect = element.getBoundingClientRect();
        return {
          label: element.getAttribute('aria-label') || element.innerText.trim().slice(0, 40) || element.placeholder || element.tagName,
          width: Math.round(rect.width),
          height: Math.round(rect.height),
        };
      })
      .filter((item) => item.width > 0 && item.height > 0 && (item.width < 44 || item.height < 44)),
  }))()
`);

const report = {
  email,
  desktopMetrics,
  drawerOpenMetrics,
  drawerClosedMetrics,
  mobileMetrics,
  authMobileMetrics,
  runtimeErrors,
  consoleErrors,
};
await fs.writeFile(
  new URL("report.json", outputDir),
  `${JSON.stringify(report, null, 2)}\n`,
);
console.log(JSON.stringify(report, null, 2));
socket.close();
