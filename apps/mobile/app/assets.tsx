import { useQuery } from "@tanstack/react-query";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  SectionList,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { apiClient } from "../src/api/client";
import { ENDPOINTS } from "../src/api/endpoints";

interface KnowledgeEntry {
  id: string;
  content_type: "text" | "audio" | "video" | "image" | "document";
  original_content_path: string | null;
  metadata: Record<string, unknown> | null;
  english_translation: string | null;
  created_at: string;
}

type CategoryMeta = { label: string; icon: React.ComponentProps<typeof Ionicons>["name"]; color: string };

const CATEGORY: Record<string, CategoryMeta> = {
  image:    { label: "Photos",    icon: "image",          color: "#22c55e" },
  document: { label: "Documents", icon: "document-text",  color: "#3b82f6" },
  audio:    { label: "Audio",     icon: "musical-notes",  color: "#8b5cf6" },
  video:    { label: "Video",     icon: "videocam",       color: "#ef4444" },
  text:     { label: "Notes",     icon: "text",           color: "#f59e0b" },
};
const ORDER = ["image", "document", "audio", "video", "text"];

function displayName(entry: KnowledgeEntry): string {
  const metaFile = entry.metadata?.filename as string | undefined;
  if (metaFile) return metaFile;
  if (entry.original_content_path) {
    return entry.original_content_path.split("/").pop() ?? entry.original_content_path;
  }
  const preview =
    entry.english_translation ??
    (entry.metadata?.original_text as string | undefined) ??
    "";
  return preview.slice(0, 50) + (preview.length > 50 ? "…" : "") || `Entry ${entry.id.slice(0, 8)}`;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export default function AssetsScreen() {
  const router = useRouter();

  const { data, isLoading, refetch, isRefetching } = useQuery<{ entries: KnowledgeEntry[] }>({
    queryKey: ["assets"],
    queryFn: async () => {
      const { data } = await apiClient.get(`${ENDPOINTS.KNOWLEDGE_ENTRIES}?page_size=200`);
      return data;
    },
  });

  const sections = ORDER.map((ct) => ({
    title: ct,
    data: (data?.entries ?? []).filter((e) => e.content_type === ct),
  })).filter((s) => s.data.length > 0);

  return (
    <SafeAreaView className="flex-1 bg-black" edges={["top", "left", "right"]}>
      {/* Header */}
      <View className="flex-row items-center gap-3 px-4 py-3 border-b border-zinc-900">
        <Pressable onPress={() => router.back()} className="active:opacity-60">
          <Ionicons name="arrow-back" size={24} color="#fff" />
        </Pressable>
        <Text className="text-white font-semibold text-lg flex-1">Assets</Text>
      </View>

      {isLoading ? (
        <View className="flex-1 items-center justify-center">
          <ActivityIndicator color="#6366f1" />
        </View>
      ) : sections.length === 0 ? (
        <View className="flex-1 items-center justify-center gap-3 px-8">
          <Ionicons name="archive-outline" size={48} color="#3f3f46" />
          <Text className="text-zinc-400 text-center">No assets yet</Text>
          <Text className="text-zinc-600 text-sm text-center">
            Upload files, photos, audio or video from the chat screen.
          </Text>
        </View>
      ) : (
        <SectionList
          sections={sections}
          keyExtractor={(item) => item.id}
          refreshControl={
            <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#6366f1" />
          }
          contentContainerStyle={{ paddingBottom: 24 }}
          stickySectionHeadersEnabled={false}
          renderSectionHeader={({ section }) => {
            const meta = CATEGORY[section.title] ?? CATEGORY.text;
            return (
              <View className="flex-row items-center gap-2 px-5 pt-5 pb-2">
                <Ionicons name={meta.icon} size={14} color={meta.color} />
                <Text className="text-zinc-400 text-xs font-semibold uppercase tracking-wider">
                  {meta.label}
                </Text>
                <Text className="text-zinc-600 text-xs">({section.data.length})</Text>
              </View>
            );
          }}
          renderItem={({ item, index, section }) => {
            const meta = CATEGORY[item.content_type] ?? CATEGORY.text;
            const name = displayName(item);
            const isLast = index === section.data.length - 1;
            return (
              <View className={`mx-4 bg-zinc-900 border-zinc-800 ${index === 0 ? "rounded-t-2xl border-t border-l border-r" : "border-l border-r"} ${isLast ? "rounded-b-2xl border-b mb-1" : "border-b border-zinc-800/50"}`}>
                <View className="flex-row items-center gap-3 px-4 py-3.5">
                  <View
                    className="w-9 h-9 rounded-xl items-center justify-center"
                    style={{ backgroundColor: meta.color + "22" }}
                  >
                    <Ionicons name={meta.icon} size={16} color={meta.color} />
                  </View>
                  <View className="flex-1">
                    <Text className="text-white text-sm font-medium" numberOfLines={1}>{name}</Text>
                    <Text className="text-zinc-500 text-xs">{formatDate(item.created_at)}</Text>
                  </View>
                </View>
              </View>
            );
          }}
        />
      )}
    </SafeAreaView>
  );
}
