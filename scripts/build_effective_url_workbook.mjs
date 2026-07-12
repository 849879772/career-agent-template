import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const inputPath = process.argv[2];
const outputPath = process.argv[3];

if (!inputPath || !outputPath) {
  throw new Error("Usage: node build_effective_url_workbook.mjs rows.json output.xlsx");
}

const rows = JSON.parse(await fs.readFile(inputPath, "utf8"));
const workbook = Workbook.create();
const sheet = workbook.worksheets.add("抓取地址核对");
sheet.showGridLines = false;

const headers = [
  "序号",
  "公司",
  "crawler",
  "配置入口",
  "实际访问地址/API",
  "访问类型",
  "推导规则",
  "需重点核对",
  "验证结果",
  "正确地址（你填写）",
  "备注",
];

const values = [headers, ...rows.map((row, idx) => [
  idx + 1,
  row.company,
  row.crawler,
  row.config_url,
  row.effective_url,
  row.access_type,
  row.rule,
  row.needs_review,
  "待验证",
  "",
  row.note,
])];

const rowCount = values.length;
const colCount = headers.length;
sheet.getRangeByIndexes(0, 0, rowCount, colCount).values = values;

const header = sheet.getRange("A1:K1");
header.format = {
  fill: "#1F4E79",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
};

const dataRange = sheet.getRangeByIndexes(0, 0, rowCount, colCount);
dataRange.format.borders = {
  insideHorizontal: { style: "thin", color: "#E5E7EB" },
  top: { style: "thin", color: "#CBD5E1" },
  bottom: { style: "thin", color: "#CBD5E1" },
};

sheet.getRangeByIndexes(1, 0, rowCount - 1, colCount).format = {
  font: { color: "#111827" },
  wrapText: true,
};

sheet.getRange("A:A").format.columnWidth = 8;
sheet.getRange("B:B").format.columnWidth = 22;
sheet.getRange("C:C").format.columnWidth = 14;
sheet.getRange("D:E").format.columnWidth = 62;
sheet.getRange("F:H").format.columnWidth = 16;
sheet.getRange("I:J").format.columnWidth = 22;
sheet.getRange("K:K").format.columnWidth = 42;
sheet.getRangeByIndexes(1, 0, rowCount - 1, colCount).format.rowHeight = 42;
sheet.freezePanes.freezeRows(1);

const table = sheet.tables.add(`A1:K${rowCount}`, true, "EffectiveCrawlerUrls");
table.style = "TableStyleMedium2";
table.showFilterButton = true;

sheet.getRange(`I2:I${rowCount}`).dataValidation = {
  rule: { type: "list", values: ["待验证", "通过", "失败", "需要更新"] },
};

sheet.getRange(`H2:H${rowCount}`).conditionalFormats.add("containsText", {
  text: "是",
  format: { fill: "#FCE4D6", font: { bold: true, color: "#9C0006" } },
});
sheet.getRange(`I2:I${rowCount}`).conditionalFormats.add("containsText", {
  text: "失败",
  format: { fill: "#FFC7CE", font: { color: "#9C0006", bold: true } },
});
sheet.getRange(`I2:I${rowCount}`).conditionalFormats.add("containsText", {
  text: "通过",
  format: { fill: "#C6EFCE", font: { color: "#006100", bold: true } },
});

const note = workbook.worksheets.add("说明");
note.showGridLines = false;
note.getRange("A1").values = [["抓取地址核对说明"]];
note.getRange("A1").format = {
  fill: "#1F4E79",
  font: { bold: true, color: "#FFFFFF", size: 14 },
};
note.getRange("A3:B9").values = [
  ["配置入口", "config.yaml 中登记的 careers_url，通常是你人工打开看的入口。"],
  ["实际访问地址/API", "crawler 真正打开或请求的列表页/API。平台型 crawler 会从配置入口推导。"],
  ["需重点核对=是", "专用 crawler 或写死入口/API，配置入口和实际访问地址可能不一致，建议优先核对。"],
  ["验证结果", "你可以选择：待验证、通过、失败、需要更新。"],
  ["正确地址（你填写）", "如果实际地址不对，请把新的校招地址填在这里。"],
  ["API", "API 行不一定能直接浏览器打开；人工核对时优先看配置入口和备注。"],
  ["更新时间", new Date().toISOString().slice(0, 10)],
];
note.getRange("A1:B9").format.wrapText = true;
note.getRange("A:A").format.columnWidth = 24;
note.getRange("B:B").format.columnWidth = 92;

await fs.mkdir(outputPath.split(/[\\/]/).slice(0, -1).join("/") || ".", { recursive: true });
const preview = await workbook.render({ sheetName: "抓取地址核对", range: "A1:K25", scale: 1, format: "png" });
await fs.writeFile(outputPath.replace(/\.xlsx$/i, ".preview.png"), new Uint8Array(await preview.arrayBuffer()));

const inspect = await workbook.inspect({
  kind: "table",
  range: "抓取地址核对!A1:K8",
  include: "values",
  tableMaxRows: 8,
  tableMaxCols: 11,
});
console.log(inspect.ndjson);

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
