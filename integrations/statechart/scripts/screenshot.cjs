// Runs inside the mermaid-cli image: screenshot each SVG to a PNG beside it.
const puppeteer = require("/home/mermaidcli/node_modules/puppeteer");
(async () => {
  const browser = await puppeteer.launch({ executablePath: "/usr/bin/chromium-browser", args: ["--no-sandbox"] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 1000, deviceScaleFactor: 2 });
  for (const svg of process.argv.slice(2)) {
    await page.goto("file://" + svg);
    await (await page.$("svg")).screenshot({ path: svg.replace(/\.svg$/, ".png") });
    console.log(svg.replace(/\.svg$/, ".png"));
  }
  await browser.close();
})();
