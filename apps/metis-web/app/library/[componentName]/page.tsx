import { notFound } from "next/navigation";

interface LibraryComponentPageProps {
  params: Promise<{
    componentName: string;
  }>;
}

export const dynamicParams = false;

export function generateStaticParams() {
  return [];
}

export default async function LibraryComponentPage({
  params,
}: LibraryComponentPageProps) {
  await params;
  notFound();
}