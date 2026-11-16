// Compta › Éditions comptables (lot NV3, claudedocs/design_navigation.md § 4) : une carte par état, l'exercice
// choisi en tête est transmis à l'édition ouverte (`?fy_id=`).
import { Anchor, Card, Group, SimpleGrid, Text } from "@mantine/core";
import { Download } from "lucide-react";
import { useList } from "../../api/resources";
import { useUrlParams } from "../../components/FilterBar";
import { AppLink } from "../../app/navigation";
import { IconTile } from "../../components/IconTile";
import { ReportFrame, type ReportMeta } from "./ReportFrame";

export interface Edition {
  key: string; title: string; icon: string; summary: string; url: string;
  exports: { label: string; url: string }[];
}

export default function ReportsHubPage() {
  const [params, setParams] = useUrlParams({ fy_id: "" });
  const { data, isFetching } = useList<Edition, ReportMeta>(["reports", "index"],
    `/api/v1/reports/${params.fy_id ? `?fy_id=${params.fy_id}` : ""}`);
  const fyId = params.fy_id || (data?.meta?.fiscal_year ? String(data.meta.fiscal_year.id) : "");
  const withFy = (url: string) => (fyId ? `${url}?fy_id=${fyId}` : url);
  return (
    <ReportFrame title="Éditions comptables" meta={data?.meta} fyId={params.fy_id}
      onFyChange={(fy_id) => setParams({ fy_id })} loading={isFetching}>
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
        {(data?.items ?? []).map((e) => (
          <Card key={e.key} withBorder padding="lg" data-testid={`edition-${e.key}`}>
            <Group gap="sm" mb="xs" wrap="nowrap">
              <IconTile icon={e.icon} />
              <Anchor component={AppLink} href={withFy(e.url)} fw={600} size="lg">{e.title}</Anchor>
            </Group>
            <Text size="sm" c="dimmed">{e.summary}</Text>
            {e.exports.length > 0 && (
              <Group gap="xs" mt="sm">
                {e.exports.map((x) => (
                  <Anchor key={x.url} href={x.url} size="sm" download>
                    <Group gap={4} wrap="nowrap"><Download size={14} aria-hidden />{x.label}</Group>
                  </Anchor>
                ))}
              </Group>
            )}
          </Card>
        ))}
      </SimpleGrid>
    </ReportFrame>
  );
}
