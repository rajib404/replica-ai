import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Pressable,
  RefreshControl,
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
  content_type: string;
  original_content_path: string | null;
  original_language: string | null;
  english_translation: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

function typeIcon(ct: string): React.ComponentProps<typeof Ionicons>["name"] {
  if (ct === "audio") return "musical-notes";
  if (ct === "video") return "videocam";
  if (ct === "image") return "image";
  if (ct === "document") return "document-text";
  return "text";
}

function typeColor(ct: string): string {
  if (ct === "audio") return "#8b5cf6";
  if (ct === "video") return "#ef4444";
  if (ct === "image") return "#22c55e";
  if (ct === "document") return "#3b82f6";
  return "#f59e0b";
}

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

export default function KnowledgeScreen() {
  const router = useRouter();
  const qc = useQueryClient();

  const { data, isLoading, refetch, isRefetching } = useQuery<{ entries: KnowledgeEntry[] }>({
    queryKey: ["knowledge-entries"],
    queryFn: async () => {
      const { data } = await apiClient.get(`${ENDPOINTS.KNOWLEDGE_ENTRIES}?page_size=100`);
      return data;
    },
  });

  const { mutate: remove } = useMutation({
    mutationFn: (id: string) => apiClient.delete(ENDPOINTS.KNOWLEDGE_ENTRY_DELETE(id)),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["knowledge-entries"] }),
  });

  const confirmDelete = (id: string, name: string) => {
    Alert.alert("Delete entry", `Remove "${name}"?`, [
      { text: "Cancel", style: "cancel" },
      { text: "Delete", style: "destructive", onPress: () => remove(id) },
    ]);
  };

  const entries = data?.entries ?? [];

  return (
    <SafeAreaView className="flex-1 bg-black" edges={["top", "left", "right"]}>
      {/* Header */}
      <View className="flex-row items-center gap-3 px-4 py-3 border-b border-zinc-900">
        <Pressable onPress={() => router.back()} className="active:opacity-60">
          <Ionicons name="arrow-back" size={24} color="#fff" />
        </Pressable>
        <Text className="text-white font-semibold text-lg flex-1">Knowledge</Text>
      </View>

      {isLoading ? (
        <View className="flex-1 items-center justify-center">
          <ActivityIndicator color="#6366f1" />
        </View>
      ) : (
        <FlatList
          data={entries}
          keyExtractor={(e) => e.id}
          refreshControl={
            <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#6366f1" />
          }
          contentContainerStyle={!entries.length ? { flex: 1 } : { paddingBottom: 24 }}
          ListEmptyComponent={
            <View className="flex-1 items-center justify-center gap-3 px-8">
              <Ionicons name="library-outline" size={48} color="#3f3f46" />
              <Text className="text-zinc-400 text-center">No knowledge entries yet</Text>
              <Text className="text-zinc-600 text-sm text-center">
                Upload documents, audio, images or video from the chat screen.
              </Text>
            </View>
          }
          ItemSeparatorComponent={() => <View className="h-px bg-zinc-900 mx-5" />}
          renderItem={({ item }) => {
            const name = displayName(item);
            const color = typeColor(item.content_type);
            return (
              <View className="flex-row items-center gap-3 px-5 py-4">
                <View
                  className="w-10 h-10 rounded-xl items-center justify-center"
                  style={{ backgroundColor: color + "22" }}
                >
                  <Ionicons name={typeIcon(item.content_type)} size={18} color={color} />
                </View>
                <View className="flex-1">
                  <Text className="text-white font-medium" numberOfLines={1}>{name}</Text>
                  <Text className="text-zinc-500 text-sm capitalize">
                    {item.content_type}
                    {item.original_language && item.original_language !== "en"
                      ? ` · ${item.original_language.toUpperCase()}`
                      : ""}
                  </Text>
                </View>
                <Pressable
                  onPress={() => confirmDelete(item.id, name)}
                  className="p-2 active:opacity-60"
                >
                  <Ionicons name="trash-outline" size={18} color="#71717a" />
                </Pressable>
              </View>
            );
          }}
        />
      )}
    </SafeAreaView>
  );
}
