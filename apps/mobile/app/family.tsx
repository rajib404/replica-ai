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

interface FamilyMember {
  id: string;
  name?: string;
  alias?: string;
  access_level?: string;
  created_at?: string;
}

const ACCESS_COLOR: Record<string, string> = {
  full: "#22c55e",
  read_only: "#f59e0b",
  limited: "#ef4444",
};

export default function FamilyScreen() {
  const router = useRouter();

  const { data, isLoading, error } = useQuery<{ members: FamilyMember[] }>({
    queryKey: ["family"],
    queryFn: async () => {
      const { data } = await apiClient.get("/api/access/members");
      return data;
    },
    retry: 1,
  });

  const members = data?.members ?? [];

  return (
    <SafeAreaView className="flex-1 bg-black" edges={["top", "left", "right"]}>
      <View className="flex-row items-center gap-3 px-4 py-3 border-b border-zinc-900">
        <Pressable onPress={() => router.back()} className="active:opacity-60">
          <Ionicons name="arrow-back" size={24} color="#fff" />
        </Pressable>
        <Text className="text-white font-semibold text-lg flex-1">Family Access</Text>
      </View>

      {isLoading ? (
        <View className="flex-1 items-center justify-center">
          <ActivityIndicator color="#6366f1" />
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 32, gap: 16 }}>
          {/* Invite note */}
          <View className="bg-indigo-500/10 border border-indigo-500/30 rounded-2xl px-4 py-4 flex-row items-center gap-3">
            <Ionicons name="information-circle" size={20} color="#6366f1" />
            <Text className="text-indigo-300 text-sm flex-1">
              Generate invite codes and manage permissions from the web dashboard.
            </Text>
          </View>

          {error ? (
            <View className="items-center gap-2 py-8">
              <Ionicons name="people-outline" size={40} color="#3f3f46" />
              <Text className="text-zinc-500 text-sm">Could not load members</Text>
            </View>
          ) : members.length === 0 ? (
            <View className="items-center gap-3 py-8">
              <Ionicons name="people-outline" size={48} color="#3f3f46" />
              <Text className="text-zinc-400">No family members yet</Text>
              <Text className="text-zinc-600 text-sm text-center">
                Invite family members from the web dashboard using an invite code or QR code.
              </Text>
            </View>
          ) : (
            <View>
              <Text className="text-zinc-500 text-xs font-semibold uppercase tracking-wider mb-2 ml-1">
                Members ({members.length})
              </Text>
              <View className="bg-zinc-900 rounded-2xl border border-zinc-800 overflow-hidden">
                {members.map((m, i) => (
                  <View key={m.id}>
                    {i > 0 && <View className="h-px bg-zinc-800 ml-14" />}
                    <View className="flex-row items-center gap-3 px-4 py-4">
                      <View className="w-10 h-10 rounded-full bg-indigo-500/20 items-center justify-center">
                        <Text className="text-indigo-300 font-bold text-sm">
                          {(m.name ?? m.alias ?? "?")[0].toUpperCase()}
                        </Text>
                      </View>
                      <View className="flex-1">
                        <Text className="text-white font-medium">{m.name ?? m.alias ?? "Member"}</Text>
                        {m.created_at && (
                          <Text className="text-zinc-500 text-xs">
                            Joined {new Date(m.created_at).toLocaleDateString()}
                          </Text>
                        )}
                      </View>
                      {m.access_level && (
                        <View
                          className="px-2 py-0.5 rounded-full"
                          style={{ backgroundColor: (ACCESS_COLOR[m.access_level] ?? "#71717a") + "22" }}
                        >
                          <Text
                            className="text-xs capitalize"
                            style={{ color: ACCESS_COLOR[m.access_level] ?? "#71717a" }}
                          >
                            {m.access_level.replace("_", " ")}
                          </Text>
                        </View>
                      )}
                    </View>
                  </View>
                ))}
              </View>
            </View>
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}
