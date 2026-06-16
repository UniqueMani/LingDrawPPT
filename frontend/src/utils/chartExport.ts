import * as echarts from "echarts";
import { inferAspectRatio } from "./pptInsert";

export async function exportEchartsOptionToPng(option: Record<string, unknown>) {
  const host = document.createElement("div");
  host.style.width = "960px";
  host.style.height = "540px";
  host.style.position = "fixed";
  host.style.left = "-10000px";
  host.style.top = "0";
  document.body.appendChild(host);
  try {
    const chart = echarts.init(host, undefined, { renderer: "svg" });
    chart.setOption(option as never, true);
    chart.resize();
    const dataUrl = chart.getDataURL({
      type: "png",
      pixelRatio: 2,
      backgroundColor: "#ffffff",
    });
    chart.dispose();
    return {
      dataUrl,
      aspectRatio: inferAspectRatio(960, 540),
    };
  } finally {
    host.remove();
  }
}
