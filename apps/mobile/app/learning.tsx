import { useQuery } from "@tanstack/react-query";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { apiClient } from "../src/api/client";
import { ENDPOINTS } from "../src/api/endpoints";

interface LearningStatus {
  enabled?: boolean;
  status?: string;
  last_cycle?: string;
  next_cycle?: string;
  messages_since_last_cycle?: number;
  total_cycles?: number;
  insights_count?: number;
}

function StatCard({ label, value, icon, color }: {
  label: string; value: string | number; icon: React.ComponentProps<typeof Ionicons>["name"]; color: string;
}) {
  return (
    <View className="flex-1 bg-zinc-900 rounded-2xl border border-zinc-800 p-4 items-center gap-1">
      <Ionicons name={icon} size={22} color={color} />
      <Text className="text-white text-xl font-bold">{value}</Text>
      <Text className="text-zinc-500 text-xs text-center">{label}</Text>
    </View>
  );
}

export default function LearningScreen() {
  const router = useRouter();

  const { data, isLoading, error } = useQuery<LearningStatus>({
    queryKey: ["learning"],
    queryFn: async () => {
      const { data } = await apiClient.get(ENDPOINTS.LEARNING_STATUS);
      return data;
    },
    retry: 1,
  });

  return (
    <SafeAreaView className="flex-1 bg-black" edges={["top", "left", "right"]}>
      <View className="flex-row items-center gap-3 px-4 py-3 border-b border-zinc-900">
        <Pressable onPress={() => router.back()} className="active:opacity-60">
          <Ionicons name="arrow-back" size={24} color="#fff" />
        </Pressable>
        <Text className="text-white font-semibold text-lg flex-1">Self-Learning</Text>
      </View>

      {isLoading ? (
        <View className="flex-1 items-center justify-center">
          <ActivityIndicator color="#6366f1" />
        </View>
      ) : error || !data ? (
        <View className="flex-1 items-center justify-center gap-3 px-8">
          <Ionicons name="school-outline" size={48} color="#3f3f46" />
          <Text className="text-zinc-400 text-center">Learning status unavailable</Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, gap: 16, paddingBottom: 32 }}>
          {/* Status pill */}
          <View className="flex-row items-center gap-2">
            <View
              className="w-2 h-2 rounded-full"
              style={{ backgroundColor: data.enabled ? "#22c55e" : "#71717a" }}
            />
            <Text className="text-zinc-400 text-sm capitalize">
              {data.status ?? (data.enabled ? "Active" : "Disabled")}
            </Text>
          </View>

          {/* Stat grid */}
          <View className="flex-row gap-3">
            <StatCard
              label="Total cycles"
              value={data.total_cycles ?? "—"}
              icon="refresh-circle"
              color="#6366f1"
            />
            <StatCard
              label="Insights"
              value={data.insights_count ?? "—"}
              icon="bulb"
              color="#f59e0b"
            />
          </View>

          <View className="flex-row gap-3">
            <StatCard
              label="Messages since cycle"
              value={data.messages_since_last_cycle ?? "—"}
              icon="chatbubbles"
              color="#06b6d4"
            />
          </View>

          {/* Timestamps */}
          <View className="bg-zinc-900 rounded-2xl border border-zinc-800 overflow-hidden">
            {data.last_cycle && (
              <View className="px-4 py-3.5">
                <Text className="text-zinc-500 text-xs mb-1">Last cycle</Text>
                <Text className="text-white text-sm">
                  {new Date(data.last_cycle).toLocaleString()}
                </Text>
              </View>
            )}
            {data.last_cycle && data.next_cycle && (
              <View className="h-px bg-zinc-800 ml-4" />
            )}
            {data.next_cycle && (
              <View className="px-4 py-3.5">
                <Text className="text-zinc-500 text-xs mb-1">Next cycle</Text>
                <Text className="text-white text-sm">
                  {new Date(data.next_cycle).toLocaleString()}
                </Text>
              </View>
            )}
          </View>
        </ScrollView>
      )}
    </SafeAreaView>
  );
}
