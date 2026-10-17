import type { Metadata } from "next";
import AssetStudio from "../AssetStudio";
import data from "../data/cybercab-studio-data.json";

export const metadata: Metadata = {
  title: "Cybercab 无限画布工作台 · VisualAgent",
  description: "Cybercab Omni 原生音画素材、边界状态、代码直播层与六轨时间线的互动审片工作台。",
};

export default async function CybercabPage({ searchParams }: { searchParams: Promise<{ variant?: string }> }) {
  const params = await searchParams;
  return <AssetStudio data={data} initialVariant={params.variant} project="cybercab" />;
}
