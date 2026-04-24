import { useQuery } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { router } from "expo-router";
import {
  ActivityIndicator,
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

interface Thread {
  id: string;
  participant_name: string;
  participant_type: string;
  last_message: string | null;
  created_at: string;
}

async function fetchThreads(): Promise<Thread[]> {
  const { data } = await apiClient.get(ENDPOINTS.CHAT_THREADS);
  return data.threads as Thread[];
}

export default function ThreadsTab() {
  const { data: threads, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ["threads"],
    queryFn: fetchThreads,
  });

  const openThread = (id: string) => router.push(`/chat/${id}`);
  const newChat = () => router.push("/chat/new");

  return (
    <SafeAreaView className="flex-1 bg-black">
      {/* Header */}
      <View className="flex-row items-center justify-between px-5 pb-3 pt-1">
        <Text className="text-white text-2xl font-bold">Chats</Text>
        <Pressable
          onPress={newChat}
          className="bg-brand rounded-full w-10 h-10 items-center justify-center active:opacity-70"
        >
          <Ionicons name="add" size={22} color="#fff" />
        </Pressable>
      </View>

      {isLoading ? (
        <View className="flex-1 items-center justify-center">
          <ActivityIndicator color="#6366f1" />
        </View>
      ) : (
        <FlatList
          data={threads ?? []}
          keyExtractor={(t) => t.id}
          refreshControl={
            <RefreshControl
              refreshing={isRefetching}
              onRefresh={refetch}
              tintColor="#6366f1"
            />
          }
          contentContainerStyle={!threads?.length ? { flex: 1 } : { paddingBottom: 24 }}
          ListEmptyComponent={
            <View className="flex-1 items-center justify-center gap-3">
              <Ionicons name="chatbubbles-outline" size={48} color="#3f3f46" />
              <Text className="text-zinc-400">No conversations yet</Text>
              <Pressable
                onPress={newChat}
                className="bg-brand px-5 py-2.5 rounded-full active:opacity-80"
              >
                <Text className="text-white font-medium">Start chatting</Text>
              </Pressable>
            </View>
          }
          ItemSeparatorComponent={() => (
            <View className="h-px bg-zinc-900 mx-5" />
          )}
          renderItem={({ item }) => (
            <Pressable
              onPress={() => openThread(item.id)}
              className="flex-row items-center gap-3 px-5 py-4 active:bg-zinc-900"
            >
              <View className="w-11 h-11 rounded-full bg-brand/20 items-center justify-center">
                <Ionicons name="person" size={20} color="#6366f1" />
              </View>
              <View className="flex-1">
                <Text className="text-white font-medium" numberOfLines={1}>
                  {item.participant_name}
                </Text>
                <Text className="text-zinc-500 text-sm" numberOfLines={1}>
                  {item.last_message ?? "No messages yet"}
                </Text>
              </View>
              <Text className="text-zinc-600 text-xs">
                {formatDistanceToNow(new Date(item.created_at), { addSuffix: true })}
              </Text>
            </Pressable>
          )}
        />
      )}
    </SafeAreaView>
  );
}
