import type { Metadata } from "next";
import AssetStudio from "./AssetStudio";
import data from "./data/studio-data.json";

export const metadata: Metadata = {
  title: "VisualAgent 广告制作台",
  description: "审阅 VisualAgent 广告片、关键画面、制作资产与时间线。",
};

export default async function Home({ searchParams }: { searchParams: Promise<{ variant?: string }> }) {
  const params = await searchParams;
  return <AssetStudio data={data} initialVariant={params.variant} />;
}
