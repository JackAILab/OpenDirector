import type { Metadata } from "next";
import IPhone18Workbench from "./IPhone18Workbench";

export const metadata: Metadata = {
  title: "iPhone 18 双语概念直播工作台 · VisualAgent",
  description: "发布会前的中英文竖屏直播预演、事实边界、弹幕回应与六轨时间线工作台。",
};

export default async function IPhone18Page({ searchParams }: { searchParams: Promise<{ variant?: string }> }) {
  const params = await searchParams;
  return <IPhone18Workbench initialVariant={params.variant} />;
}
