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
import { Ionicons } from "@expo/vector-icons";
import { apiClient } from "../../src/api/client";
import { ENDPOINTS } from "../../src/api/endpoints";

interface KnowledgeEntry {
  id: string;
  title: string;
  source_type: string;
  created_at: string;
  chunk_count?: number;
}

async function fetchEntries(): Promise<KnowledgeEntry[]> {
  const { data } = await apiClient.get(ENDPOINTS.KNOWLEDGE_ENTRIES);
  return data.entries ?? data ?? [];
}

async function deleteEntry(id: string): Promise<void> {
  await apiClient.delete(ENDPOINTS.KNOWLEDGE_ENTRY_DELETE(id));
}

function sourceIcon(type: string): React.ComponentProps<typeof Ionicons>["name"] {
  if (type === "pdf") return "document-text";
  if (type === "url") return "globe";
  if (type === "text") return "text";
  return "folder";
}

export default function KnowledgeTab() {
  const qc = useQueryClient();
  const { data: entries, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ["knowledge"],
    queryFn: fetchEntries,
  });

  const { mutate: remove } = useMutation({
    mutationFn: deleteEntry,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["knowledge"] }),
  });

  const confirmDelete = (id: string, title: string) => {
    Alert.alert("Delete entry", `Remove "${title}" from your knowledge base?`, [
      { text: "Cancel", style: "cancel" },
      { text: "Delete", style: "destructive", onPress: () => remove(id) },
    ]);
  };

  return (
    <SafeAreaView className="flex-1 bg-black">
      <View className="flex-row items-center justify-between px-5 pb-3 pt-1">
        <Text className="text-white text-2xl font-bold">Knowledge</Text>
        <View className="bg-zinc-800 rounded-full px-3 py-1">
          <Text className="text-zinc-400 text-xs">Upload via web app</Text>
        </View>
      </View>

      {isLoading ? (
        <View className="flex-1 items-center justify-center">
          <ActivityIndicator color="#6366f1" />
        </View>
      ) : (
        <FlatList
          data={entries ?? []}
          keyExtractor={(e) => e.id}
          refreshControl={
            <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#6366f1" />
          }
          contentContainerStyle={!entries?.length ? { flex: 1 } : { paddingBottom: 24 }}
          ListEmptyComponent={
            <View className="flex-1 items-center justify-center gap-3">
              <Ionicons name="library-outline" size={48} color="#3f3f46" />
              <Text className="text-zinc-400">No knowledge entries yet</Text>
              <Text className="text-zinc-600 text-sm text-center px-8">
                Upload documents from the web dashboard to see them here.
              </Text>
            </View>
          }
          ItemSeparatorComponent={() => <View className="h-px bg-zinc-900 mx-5" />}
          renderItem={({ item }) => (
            <View className="flex-row items-center gap-3 px-5 py-4">
              <View className="w-10 h-10 rounded-xl bg-zinc-800 items-center justify-center">
                <Ionicons name={sourceIcon(item.source_type)} size={18} color="#6366f1" />
              </View>
              <View className="flex-1">
                <Text className="text-white font-medium" numberOfLines={1}>
                  {item.title}
                </Text>
                <Text className="text-zinc-500 text-sm capitalize">
                  {item.source_type}
                  {item.chunk_count ? ` · ${item.chunk_count} chunks` : ""}
                </Text>
              </View>
              <Pressable
                onPress={() => confirmDelete(item.id, item.title)}
                className="p-2 active:opacity-60"
              >
                <Ionicons name="trash-outline" size={18} color="#71717a" />
              </Pressable>
            </View>
          )}
        />
      )}
    </SafeAreaView>
  );
}
